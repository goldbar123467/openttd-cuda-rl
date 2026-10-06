/* Development-only offline replay of recorded native command packets. Included
 * after rl_v2_live.inc so observations use the exact public live boundary. */

extern void RlHumanDispatch(Commands command, StringID message, CompanyID company, const CommandDataBuffer &data);
extern CommandCost _rl_human_command_result;
extern bool _rl_human_command_result_seen;

namespace {
static uint32_t HumanInteger(std::string_view text, int base)
{
    uint32_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value, base);
    Require(result.ec == std::errc{} && result.ptr == text.data() + text.size(), "invalid human replay integer");
    return value;
}

static json HumanSnapshot()
{
    CandidateEnumeration enumeration;
    json state = DevObservation(enumeration, 0, 512, 1, false, false, DEV_LIVE_SCHEMA, true);
    state["date"] = TimerGameEconomy::date.base();
    state["date_fraction"] = TimerGameEconomy::date_fract;
    // Complete serialization is retained for independent checkpoint validation.
    json orders = json::array();
    for (const Vehicle *vehicle : Vehicle::Iterate()) if (vehicle->owner == _current_company && vehicle->IsPrimaryVehicle()) {
        json list = json::array();
        for (const Order &order : vehicle->Orders()) list.push_back({{"type", static_cast<uint8_t>(order.GetType())},
            {"destination", order.GetDestination().base()}, {"serialized", EndianBufferWriter<CommandDataBuffer>::FromValue(order)}});
        orders.push_back({{"vehicle_id", vehicle->index.base()}, {"orders", list}});
    }
    state["exact_orders"] = orders;
    return state;
}

static void HumanWrite(const std::filesystem::path &path, const json &value)
{
    std::ofstream stream(path); stream << value.dump() << '\n';
    Require(static_cast<bool>(stream), "human replay artifact write failed");
}

static void HumanLoad(const std::string &path)
{
    _game_mode = GM_NORMAL;
    Require(SaveOrLoad(path, SLO_LOAD, DFT_GAME_FILE, NO_DIRECTORY, false) == SL_OK,
        "human replay save load failed");
    SetModalProgress(false);
    SetLocalCompany(CompanyID::Begin());
    _current_company = CompanyID::Begin();
}

static bool HumanCandidateMatches(const json &event, const Candidate &candidate)
{
    if (event.at("company").get<uint16_t>() != CompanyID::Begin().base()) return false;
    const std::string name = event.at("name");
    const auto &p = candidate.parameters;
    // GUI client IDs may restore saved vehicle orders; the policy's purchase
    // does not. Never label such a purchase as equivalent.
    if (candidate.family == Family::BuyBus && OrderBackup::GetNumItems() != 0) return false;
    const auto args = event.value("mapping", json::object());
    if (!args.contains("family") || args.at("family") != FAMILY_NAMES[static_cast<size_t>(candidate.family)]) return false;
    for (auto it = args.at("parameters").begin(); it != args.at("parameters").end(); ++it) {
        const size_t index = HumanInteger(it.key(), 10);
        if (index >= p.size() || p[index] != it.value().get<uint32_t>()) return false;
    }
#ifdef RL_DEV_BUS_ORDERS
    if (_dev_bus_orders && candidate.family == Family::SetRoute) {
        CommandDataBuffer expected;
        auto word = [&](uint32_t value) { for (size_t i = 0; i < 4; ++i) expected.push_back(static_cast<uint8_t>(value >> (8 * i))); };
        const uint8_t operation = p[2] & 0xFF, index = (p[2] >> 8) & 0xFF;
        Commands command = CMD_INSERT_ORDER;
        std::string_view command_name;
        if (operation == 3) {
            command = CMD_CLONE_ORDER; command_name = "CmdCloneOrder";
            expected.push_back(CO_COPY); word(p[1]); word(p[3]);
        } else {
            word(p[1]); expected.push_back(index);
            if (operation == 1) {
                command_name = "CmdInsertOrder";
                Order order{static_cast<uint8_t>(p[2] >> 16), static_cast<uint8_t>(p[2] >> 24), DestinationID{static_cast<uint16_t>(p[3])}};
                const auto bytes = DevOrderBytes(order); expected.insert(expected.end(), bytes.begin(), bytes.end());
            } else if (operation == 2) {
                command = CMD_MODIFY_ORDER; command_name = "CmdModifyOrder";
                expected.push_back(MOF_LOAD); expected.push_back(p[3]); expected.push_back(p[3] >> 8);
            } else if (operation == 4) { command = CMD_DELETE_ORDER; command_name = "CmdDeleteOrder"; }
            else return false;
        }
        if (event.at("command").get<uint32_t>() != static_cast<uint32_t>(command) || name != command_name) return false;
        const std::string payload = event.at("payload");
        if (payload.size() != expected.size() * 2) return false;
        for (size_t i = 0; i < expected.size(); ++i)
            if (HumanInteger(payload.substr(i * 2, 2), 16) != expected[i]) return false;
    }
#endif
    return true;
}

#ifdef RL_DEV_BUS_ORDERS
static json HumanOrderState()
{
    json state = json::object();
    for (const Vehicle *vehicle : Vehicle::Iterate()) if (vehicle->owner == _current_company && vehicle->IsPrimaryVehicle()) {
        json orders = json::array();
        for (const Order &order : vehicle->Orders()) orders.push_back(DevOrderBytes(order));
        state[fmt::format("{}", vehicle->index.base())] = orders;
    }
    return state;
}

static void HumanVerifyOrderCandidate(const Candidate &candidate, const std::filesystem::path &output, int line)
{
    const auto save = output / fmt::format("native-semantic-before-{}.sav", line);
    Require(SaveOrLoad(save.string(), SLO_SAVE, DFT_GAME_FILE, NO_DIRECTORY, false) == SL_OK, "native semantic test save failed");
    const auto &p = candidate.parameters;
    const std::string target = fmt::format("{}", p[1]);
    const uint operation = p[2] & 0xFF, index = (p[2] >> 8) & 0xFF;
    const json before = HumanOrderState(); json expected = before;
    if (operation == 1) {
        Order order{static_cast<uint8_t>(p[2] >> 16), static_cast<uint8_t>(p[2] >> 24), DestinationID{static_cast<uint16_t>(p[3])}};
        expected[target].insert(expected[target].begin() + index, DevOrderBytes(order));
    } else if (operation == 2) {
        const uint8_t flags = expected[target][index][1].get<uint8_t>();
        expected[target][index][1] = (flags & ~0x70U) | (p[3] << 4);
    } else if (operation == 3) {
        expected[target] = before.at(fmt::format("{}", p[3]));
    } else if (operation == 4) expected[target].erase(expected[target].begin() + index);
    const json result = ExecuteCandidate(candidate);
    const json actual = HumanOrderState();
    Require(result.at("status") == "SUCCESS" && actual == expected,
        "native order candidate did not execute its exact serialized semantics");
    json checks = {"candidate-executes", "exact-resulting-order-bytes", "unrelated-vehicles-unchanged"};
    const Vehicle *vehicle = Vehicle::Get(VehicleID{p[1]});
    if (operation == 2) {
        auto alternate = p; alternate[3] = p[3] == 3 ? 2 : 3;
        Require(DevBusOrderCommand(alternate, DoCommandFlag::Execute).Succeeded(), "alternate full-load semantic test failed");
        json alternate_expected = expected;
        const uint8_t flags = alternate_expected[target][index][1].get<uint8_t>();
        alternate_expected[target][index][1] = (flags & ~0x70U) | (alternate[3] << 4);
        Require(HumanOrderState() == alternate_expected && alternate_expected != expected,
            "Full load any and Full load all did not preserve distinct exact flags");
        Require(DevBusOrderCommand(p, DoCommandFlag::Execute).Succeeded() && HumanOrderState() == expected,
            "full-load test did not preserve non-stop/unload and unrelated order fields");
        checks.push_back("full-load-any-distinct-from-full-load-all");
        checks.push_back("load-change-preserves-non-stop-unload-and-timetable");
    }
    if (operation == 3) {
        Require(!vehicle->IsOrderListShared(), "CO_COPY produced shared orders");
        std::array<uint32_t, PARAMETER_WORDS> change{}; change[1] = p[3]; change[2] = 2U | (MOF_LOAD << 16);
        const Vehicle *source = Vehicle::Get(VehicleID{p[3]});
        change[3] = source->GetOrder(0)->GetLoadType() == OrderLoadType::FullLoadAny ? 2 : 3;
        Require(DevBusOrderCommand(change, DoCommandFlag::Execute).Succeeded(), "copy independence test could not change source");
        Require(HumanOrderState().at(target) == expected.at(target), "copied orders alias source after modification");
        checks.push_back("copy-independent-after-source-mutation");
    }
    const json before_rejection = HumanOrderState();
    auto invalid = p; invalid[2] = 4U | (static_cast<uint32_t>(vehicle->GetNumOrders()) << 8); invalid[3] = 0;
    Require(DevBusOrderCommand(invalid, DoCommandFlag::Execute).Failed() && HumanOrderState() == before_rejection,
        "out-of-range order deletion changed state");
    checks.push_back("out-of-range-delete-rejected-without-mutation");
    invalid[1] = UINT32_MAX;
    Require(DevBusOrderCommand(invalid, DoCommandFlag::Execute).Failed() && HumanOrderState() == before_rejection,
        "invalid vehicle order action changed state");
    checks.push_back("invalid-vehicle-rejected-without-mutation");
    HumanWrite(output / fmt::format("native-semantic-command-{}.json", line),
        {{"status", "passed"}, {"line", line}, {"parameters", p}, {"before", before}, {"expected_after", expected},
            {"actual_after", actual}, {"action", result}, {"checks", checks}});
    HumanLoad(save.string());
    Require(HumanOrderState() == before, "native semantic test failed to restore source state");
}
#endif
}

void RunRlHumanReplay(const std::string &config_path)
{
    const json config = ReadCanonicalJson(config_path);
    const std::filesystem::path output = config.at("output").get<std::string>();
    std::filesystem::create_directories(output / "samples");
#ifdef RL_DEV_BUS_ORDERS
    _dev_bus_orders = config.value("observation_mode", "finance-v1") == "orders-v1";
    ACTION_SCHEMA_ID = _dev_bus_orders ? DEV_ORDER_ACTION_SCHEMA : "v2-m15-hierarchical-action-v1";
#endif
    HumanLoad(config.at("initial_save"));
    HumanWrite(output / "initial.json", HumanSnapshot());
    std::ofstream trace(output / "commands.jsonl");
    json samples = json::array();
    size_t commands = 0;
    for (const json &event : config.at("events")) {
        const int date = event.at("date"); const uint fraction = event.at("fraction");
        uint64_t ticks = 0;
        while (TimerGameEconomy::date.base() < date || (TimerGameEconomy::date.base() == date && TimerGameEconomy::date_fract < fraction)) {
            // StateGameLoop polls and releases native link-graph job pauses.
            // Keep human/control pauses fatal when the next event needs time
            // to advance; never clear a pause or synthesize an unpause command.
            Require(_pause_mode.None() || _pause_mode == PauseMode::LinkGraph ||
                _pause_mode.base() == PauseModes{PauseMode::LinkGraph, PauseMode::CommandDuringPause}.base(),
                fmt::format("human replay cannot advance a paused game to next command: mode={}", _pause_mode.base()));
            StateGameLoop();
            Require(++ticks < 1000000, "human replay event tick bound exceeded");
        }
        Require(TimerGameEconomy::date.base() == date && TimerGameEconomy::date_fract == fraction,
            "human replay event was passed");
        if (event.at("kind") == "checkpoint") {
            HumanWrite(output / "replayed.json", HumanSnapshot());
            Require(SaveOrLoad((output / "replayed.sav").string(), SLO_SAVE, DFT_GAME_FILE, NO_DIRECTORY, false) == SL_OK,
                "human replay result save failed");
            break;
        }
        _current_company = CompanyID::Begin();
        if (config.contains("export_before_lines")) for (const auto &line : config.at("export_before_lines")) if (line == event.at("line")) {
            const auto path = output / fmt::format("before-command-{}.sav", event.at("line").get<int>());
            Require(SaveOrLoad(path.string(), SLO_SAVE, DFT_GAME_FILE, NO_DIRECTORY, false) == SL_OK, "human replay context export failed");
        }
        CandidateEnumeration enumeration = EnumerateCandidates();
        std::optional<json> sample;
        std::optional<Candidate> sample_candidate;
        std::optional<int64_t> sample_test_cost;
        size_t offset = 0;
        for (size_t family = 0; family < FAMILY_COUNT; ++family) {
          size_t row = offset;
          for (const Candidate &candidate : enumeration.selected[family]) {
            if (HumanCandidateMatches(event, candidate)) {
                Require(!sample.has_value(), "human replay action mapping is ambiguous");
                sample_test_cost = candidate.cost.base();
                sample_candidate = candidate;
                const auto stem = fmt::format("command-{}", event.at("line").get<int>());
                auto observation = output / "samples" / (stem + "-observation.json");
                auto metadata = output / "samples" / (stem + "-tensor.json");
                auto candidates = output / "samples" / (stem + "-candidates.json");
                HumanWrite(observation, HumanSnapshot());
                const std::string sha = DevWritePublicTensors(metadata, true);
                WriteRlV2CandidatesAndMaybeExecute(candidates.string(), "", "", sha, 0, 0, 0);
                json legal = json::array(); size_t legal_offset = 0;
                for (size_t f = 0; f < FAMILY_COUNT; ++f) {
                    for (size_t i = 0; i < enumeration.selected[f].size(); ++i) legal.push_back(legal_offset + i);
                    legal_offset += FAMILY_QUOTAS[f];
                }
                auto binary = metadata; binary.replace_extension(".bin");
                auto candidate_binary = candidates; candidate_binary.replace_extension(".bin");
                sample = {{"sample_id", stem}, {"game_id", config.at("game_id")}, {"split", "train"},
                    {"observation_path", observation.string()}, {"observation_tensor_path", binary.string()},
                    {"observation_metadata_path", metadata.string()}, {"candidate_metadata_path", candidates.string()},
                    {"candidate_tensor_path", candidate_binary.string()}, {"action_row", row}, {"action_family", family},
                    {"legal_rows", legal}, {"candidate_key", candidate.stable_key}, {"source_command_index", event.at("line")}};
                (*sample)["operation"] = event.value("operation", "unknown");
                (*sample)["source_command"] = event;
            }
            ++row;
          }
          offset += FAMILY_QUOTAS[family];
        }
#ifdef RL_DEV_BUS_ORDERS
        if (_dev_bus_orders && sample_candidate && sample_candidate->family == Family::SetRoute)
            HumanVerifyOrderCandidate(*sample_candidate, output, event.at("line").get<int>());
#endif
        const Company *company = Company::Get(CompanyID::Begin());
        const int64_t before_cash = company->money.base(), before_loan = company->current_loan.base();
        CommandDataBuffer data;
        const std::string payload = event.at("payload");
        for (size_t i = 0; i < payload.size(); i += 2) data.push_back(static_cast<uint8_t>(HumanInteger(payload.substr(i, 2), 16)));
        _rl_human_command_result_seen = false;
        RlHumanDispatch(static_cast<Commands>(event.at("command").get<uint32_t>()), event.at("message").get<uint32_t>(),
            static_cast<CompanyID>(event.at("company").get<uint16_t>()), data);
        _current_company = CompanyID::Begin();
        Require(_rl_human_command_result_seen, "human replay command produced no confirmed result");
        const int64_t cost = _rl_human_command_result.GetCost().base();
        json result = {{"source_command_index", event.at("line")}, {"name", event.at("name")}, {"date", date}, {"fraction", fraction},
            {"succeeded", _rl_human_command_result.Succeeded()}, {"command_cost", cost},
            {"before_cash", before_cash}, {"after_cash", company->money.base()}, {"before_loan", before_loan}, {"after_loan", company->current_loan.base()},
            {"error_message_id", _rl_human_command_result.GetErrorMessage()}};
        result["supported_policy_label"] = sample.has_value();
        trace << result.dump() << '\n'; trace.flush();
        Require(_rl_human_command_result.Succeeded(), "recorded successful command failed during replay");
        Require(!sample_test_cost || *sample_test_cost == cost, "mapped native candidate and replayed command cost differ");
        Require(company->money.base() - before_cash == company->current_loan.base() - before_loan - cost,
            "human replay command cash/debt/cost accounting differs");
        if (sample) {
            const auto after_path = output / "samples" / fmt::format("command-{}-after-observation.json", event.at("line").get<int>());
            HumanWrite(after_path, HumanSnapshot());
            (*sample)["after_observation_path"] = after_path.string();
            (*sample)["command_cost"] = cost; samples.push_back(*sample);
        }
        ++commands;
    }
    HumanWrite(output / "samples.json", samples);
    HumanLoad(config.at("checkpoint_save"));
    HumanWrite(output / "checkpoint.json", HumanSnapshot());
    HumanWrite(output / "native-result.json", {{"status", "replay_executed"}, {"commands", commands}, {"samples", samples.size()}});
}
