/* Development-only interactive adapter included by rl_v2_action.cpp.
 * Reuses its native candidate enumeration/execution. No corpus rewards.
 * The including file supplies OpenTTD headers and POSIX/chrono headers before
 * safeguards.h. This is not part of the historical patch series. */

namespace {
static constexpr std::string_view DEV_LIVE_SCHEMA = "openttd-rl-development-v2-live-1";
static constexpr std::string_view DEV_SHARED_SCHEMA = "openttd-rl-development-v2-shared-1";

static bool DevReadExact(int fd, uint8_t *output, size_t length, bool allow_eof,
    std::chrono::steady_clock::time_point deadline)
{
    size_t offset = 0;
    while (offset < length) {
        auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now()).count();
        Require(remaining > 0, "development bridge idle timeout; simulation remained paused");
        pollfd descriptor{fd, POLLIN, 0};
        int ready = ::poll(&descriptor, 1, static_cast<int>(remaining));
        if (ready < 0 && errno == EINTR) continue;
        Require(ready > 0, "development bridge read timeout/error");
        auto received = ::read(fd, output + offset, length - offset);
        if (received < 0 && errno == EINTR) continue;
        if (received == 0 && offset == 0 && allow_eof) return false;
        Require(received > 0, "development bridge truncated frame");
        offset += static_cast<size_t>(received);
    }
    return true;
}

static std::optional<json> DevReadRequest(int fd)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(60);
    std::array<uint8_t, 4> header{};
    if (!DevReadExact(fd, header.data(), header.size(), true, deadline)) return std::nullopt;
    uint32_t size = static_cast<uint32_t>(header[0]) | (static_cast<uint32_t>(header[1]) << 8) |
        (static_cast<uint32_t>(header[2]) << 16) | (static_cast<uint32_t>(header[3]) << 24);
    Require(size > 0 && size <= 16384, "development request frame exceeds bound");
    std::vector<uint8_t> bytes(size);
    DevReadExact(fd, bytes.data(), bytes.size(), false, deadline);
    std::string text(bytes.begin(), bytes.end());
    json request = json::parse(text);
    Require(request.is_object() && request.dump() == text, "development request is not canonical JSON");
    return request;
}

static void DevWriteResponse(int fd, const json &response)
{
    std::string text = response.dump();
    Require(text.size() <= 4 * 1024 * 1024, "development response exceeds bound");
    std::vector<uint8_t> bytes;
    bytes.reserve(text.size() + 4);
    AppendU32(bytes, static_cast<uint32_t>(text.size()));
    bytes.insert(bytes.end(), text.begin(), text.end());
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(60);
    size_t offset = 0;
    while (offset < bytes.size()) {
        auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now()).count();
        Require(remaining > 0, "development bridge write timeout");
        pollfd descriptor{fd, POLLOUT, 0};
        int ready = ::poll(&descriptor, 1, static_cast<int>(remaining));
        if (ready < 0 && errno == EINTR) continue;
        Require(ready > 0, "development bridge write timeout/error");
        auto written = ::write(fd, bytes.data() + offset, bytes.size() - offset);
        if (written < 0 && errno == EINTR) continue;
        Require(written > 0, "development bridge response write failed");
        offset += static_cast<size_t>(written);
    }
}

static json DevCompanyEconomy(CompanyID identity = _current_company)
{
    const Company *company = Company::GetIfValid(identity);
    if (company == nullptr) return {{"alive", false}};
    CargoType passengers = GetCargoTypeByLabel(CT_PASSENGERS);
    Require(IsValidCargoType(passengers), "development passenger cargo missing");
    int64_t income = 0, expenses = 0, delivered = 0;
    auto add = [&](const CompanyEconomyEntry &entry) {
        income += entry.income.base(); expenses += entry.expenses.base(); delivered += entry.delivered_cargo[passengers];
    };
    add(company->cur_economy);
    // This adapter limits episodes to 65536 ticks, shorter than the retained
    // economy history. Summing quarters avoids the cur_economy reset pitfall.
    for (uint8_t i = 0; i < company->num_valid_stat_ent; ++i) add(company->old_economy[i]);
    return {{"alive", company->months_of_bankruptcy < 10}, {"balance", company->money.base()},
        {"loan", company->current_loan.base()}, {"income", income}, {"expenses", expenses},
        {"operating_profit", income + expenses}, {"delivered_passengers", delivered}};
}

static std::string DevWritePublicTensors(const std::filesystem::path &metadata_path)
{
    // Reuse the native encoder, then redact non-public feature slots before
    // publishing a response or giving their paths to any policy process.
    WriteRlV2Observation(metadata_path.string(), 0, 0, 0, true);
    auto binary_path = metadata_path; binary_path.replace_extension(".bin");
    Require(std::filesystem::file_size(binary_path) == 2182927, "native observation layout changed");
    std::vector<uint8_t> bytes(2182927);
    {
        std::ifstream input(binary_path, std::ios::binary);
        input.read(reinterpret_cast<char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
        Require(static_cast<bool>(input), "cannot read native tensor observation");
    }
    // M15 vehicle columns 7/8 expose breakdown delay/countdown. A countdown
    // can reveal a future failure; neither field is available to live agents.
    for (size_t row = 0; row < 1024; ++row) {
        const size_t offset = 1286927 + (row * 40 + 7) * sizeof(float);
        std::fill(bytes.begin() + offset, bytes.begin() + offset + 2 * sizeof(float), uint8_t{0});
    }
    Sha256 digest; digest.Update(bytes); const std::string sha = digest.Finish();
    json metadata = ReadCanonicalJson(metadata_path.string());
    metadata["source_observation_schema_id"] = metadata.at("observation_schema_id");
    metadata["observation_schema_id"] = "v2-m15-public-development-v2";
    metadata["schema_version"] = "openttd-rl-development-v2-observation-metadata-1";
    metadata["redacted_features"] = {"structured[13:16]", "entities.vehicles.values[:,7:9]"};
    metadata["vehicle_order"] = "own-company-first-then-public-vehicle-id";
    metadata["observing_company"] = _current_company.base();
    metadata["binary"]["sha256"] = sha;
    {
        std::ofstream output(binary_path, std::ios::binary | std::ios::trunc);
        output.write(reinterpret_cast<const char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
        Require(static_cast<bool>(output), "cannot publish public tensor observation");
    }
    {
        std::ofstream output(metadata_path, std::ios::binary | std::ios::trunc);
        output << metadata.dump() << '\n';
        Require(static_cast<bool>(output), "cannot publish public observation metadata");
    }
    return sha;
}

static json DevObservation(CandidateEnumeration &enumeration, uint32_t decisions, uint32_t maximum,
    uint32_t step_ticks, bool pending, bool terminal, std::string_view schema = DEV_LIVE_SCHEMA)
{
    const CompanyID identity = _current_company;
    if (terminal && Company::GetIfValid(identity) == nullptr) {
        return {{"schema_version", schema}, {"company_id", identity.base()}, {"tick", TimerGameTick::counter},
            {"decisions", decisions}, {"terminal", true}, {"truncated", false}, {"pending_step", pending},
            {"economy", DevCompanyEconomy()}, {"candidates", json::array()}};
    }
    Require(Company::GetNumItems() <= 2 && Company::IsValidID(identity), "development observing company missing");
    json towns = json::array(), stations = json::array(), depots = json::array(), vehicles = json::array(), roads = json::array();
    json clear_tiles = json::array(), houses = json::array(), flat_tiles = json::array();
    const CargoType passengers = GetCargoTypeByLabel(CT_PASSENGERS);
    const uint catchment = _settings_game.station.modified_catchment ? CA_BUS : CA_UNMODIFIED;
    for (const Town *town : Town::Iterate()) towns.push_back({{"id", town->index.base()}, {"tile", town->xy.base()},
        {"x", TileX(town->xy)}, {"y", TileY(town->xy)}, {"population", town->cache.population}});
    for (const Station *station : Station::Iterate()) if (station->owner == identity) {
        const GoodsEntry &goods = station->goods[passengers];
        stations.push_back({{"id", station->index.base()}, {"tile", station->xy.base()},
            {"catchment_radius", station->GetCatchmentRadius()}, {"accepts_passengers", goods.status.Test(GoodsEntry::State::Acceptance)},
            {"waiting_passengers", goods.AvailableCount()}, {"passenger_rating", goods.rating}});
    }
    for (const Depot *depot : Depot::Iterate()) if (IsRoadDepotTile(depot->xy) && GetTileOwner(depot->xy) == identity) {
        depots.push_back({{"id", depot->index.base()}, {"tile", depot->xy.base()}});
    }
    for (const Vehicle *vehicle : Vehicle::Iterate()) if (vehicle->owner == identity && vehicle->type == VEH_ROAD && vehicle->IsPrimaryVehicle()) {
        json orders = json::array();
        for (const Order &order : vehicle->Orders()) orders.push_back({{"type", static_cast<uint8_t>(order.GetType())}, {"destination", order.GetDestination().base()}});
        vehicles.push_back({{"id", vehicle->index.base()}, {"tile", vehicle->tile.base()},
            {"stopped", vehicle->vehstatus.Test(VehState::Stopped)}, {"orders", orders},
            {"speed", vehicle->cur_speed}, {"destination_tile", vehicle->dest_tile.base()},
            {"cargo_count", vehicle->cargo.StoredCount()}, {"cargo_capacity", vehicle->cargo_cap}});
    }
    for (TileIndex tile{}; tile < Map::Size(); ++tile) {
        RoadBits bits = GetAnyRoadBits(tile, RTT_ROAD);
        if (bits != ROAD_NONE) roads.push_back({tile.base(), static_cast<uint8_t>(bits)});
        if (IsTileType(tile, MP_CLEAR)) clear_tiles.push_back(tile.base());
        if (IsTileType(tile, MP_HOUSE)) houses.push_back(tile.base());
        if (GetTileSlope(tile) == SLOPE_FLAT) flat_tiles.push_back(tile.base());
    }
    enumeration = EnumerateCandidates();
    json candidates = json::array();
    if (!pending && !terminal && decisions < maximum) {
        for (size_t family = 0; family < FAMILY_COUNT; ++family) for (const Candidate &candidate : enumeration.selected[family]) {
            json entry = {{"key", candidate.stable_key}, {"family", FAMILY_NAMES[family]},
                {"family_index", family}, {"parameters", candidate.parameters}, {"features", candidate.features},
                {"cost", candidate.cost.base()}};
            if (candidate.family == Family::BuildBusStop) {
                // The construction GUI exposes present catchment acceptance
                // and supply. These queries do not step the game or predict it.
                TileIndex tile{candidate.parameters[1]};
                entry["passenger_acceptance_eighths"] = GetAcceptanceAroundTiles(tile, 1, 1, catchment)[passengers];
                entry["passenger_production"] = GetProductionAroundTiles(tile, 1, 1, catchment)[passengers];
            }
            candidates.push_back(std::move(entry));
        }
    }
    // Public/own-company fields only. Reset seeds, RNG state and future outcomes
    // are retained by the launcher, never exposed in the policy observation.
    return {{"schema_version", schema}, {"action_schema_id", ACTION_SCHEMA_ID}, {"company_id", identity.base()},
        {"token", NativeStateSha256()}, {"tick", TimerGameTick::counter}, {"decisions", decisions},
        {"maximum_decisions", maximum}, {"step_ticks", step_ticks}, {"pending_step", pending},
        {"terminal", terminal}, {"truncated", !terminal && decisions >= maximum},
        {"economy", DevCompanyEconomy()}, {"map", {{"width", Map::SizeX()}, {"height", Map::SizeY()},
            {"roads", roads}, {"clear_tiles", clear_tiles}, {"houses", houses}, {"flat_tiles", flat_tiles},
            {"bus_stop_catchment_radius", catchment}}},
        {"towns", towns}, {"stations", stations}, {"depots", depots}, {"vehicles", vehicles}, {"candidates", candidates}};
}

static void RunDevelopmentV2Live(const json &config, const std::string &trace_path, const std::string &artifact_directory)
{
    const bool shared = config.at("schema_version") == DEV_SHARED_SCHEMA;
    const std::string_view schema = shared ? DEV_SHARED_SCHEMA : DEV_LIVE_SCHEMA;
    Require(config.size() == (shared ? 7 : 6) && config.at("schema_version") == schema &&
        (shared || config.at("company_id") == 0), "development live configuration fields differ");
    if (shared) Require(config.at("company_count").is_number_unsigned() && config.at("company_count") == 2,
        "shared development requires exactly two companies");
    for (const char *name : {"company_id", "input_fd", "output_fd", "step_ticks", "maximum_decisions"}) {
        Require(config.at(name).is_number_unsigned(), "development configuration needs unsigned integers");
    }
    const int input = config.at("input_fd").get<int>(), output = config.at("output_fd").get<int>();
    const uint32_t ticks = config.at("step_ticks").get<uint32_t>(), maximum = config.at("maximum_decisions").get<uint32_t>();
    const uint32_t companies = shared ? 2 : 1, first_company = config.at("company_id").get<uint32_t>();
    Require(input >= 3 && output >= 3 && input != output && ticks >= 1 && ticks <= 128 && maximum >= 1 && maximum <= 512,
        "development live descriptor/timing bounds differ");
    Require(first_company < companies && (!shared || maximum % companies == 0), "shared action budgets must be balanced");
    Require(Map::SizeX() <= 128 && Map::SizeY() <= 128, "initial live adapter limits development maps to 128x128");
    Require(std::filesystem::is_directory(artifact_directory) && !std::filesystem::exists(trace_path), "development artifact paths invalid");
    Require(Company::GetNumItems() == 1 && Company::IsValidID(CompanyID::Begin()), "unexpected initial companies");
    if (shared) {
        Company *second = DoStartupNewCompany(false, CompanyID{1});
        const Company *first = Company::Get(CompanyID::Begin());
        Require(second != nullptr && second->index == CompanyID{1} && second->money == first->money &&
            second->current_loan == first->current_loan, "shared companies must start with equal cash and debt");
    }
    _current_company = CompanyID{static_cast<uint8_t>(first_company)};
    std::ofstream trace(trace_path, std::ios::binary);
    Require(static_cast<bool>(trace), "cannot create development live trace");
    uint64_t request_id = 1;
    uint32_t decisions = 0;
    bool pending = false, terminal = false;
    CandidateEnumeration enumeration;
    json action, before;
    std::string before_hash;
    json final = {{"schema_version", schema}, {"status", "CLOSED"}, {"company_id", first_company}};
    if (shared) {
        final["initial_tick"] = TimerGameTick::counter;
        final["initial_companies"] = json::array();
        for (uint32_t company = 0; company < companies; ++company)
            final["initial_companies"].push_back({{"company_id", company}, {"economy", DevCompanyEconomy(CompanyID{static_cast<uint8_t>(company)})}});
    }
    try {
        while (auto incoming = DevReadRequest(input)) {
            const json &request = *incoming;
            Require(request.contains("id") && request.at("id").is_number_unsigned() && request.at("id") == request_id,
                "development request identity out of order");
            Require(request.contains("company_id") && request.contains("operation") && request.at("operation").is_string(), "development request fields missing");
            json response = {{"schema_version", schema}, {"id", request_id++}, {"status", "OK"}};
            std::string operation = request.at("operation").get<std::string>();
            bool close = false;
            const uint32_t expected_company = (first_company + decisions) % companies;
            if (!request.at("company_id").is_number_unsigned() || request.at("company_id").get<uint64_t>() >= companies) {
                response.update({{"status", "REJECTED"}, {"reason", "COMPANY_SCOPE"}});
            } else if (shared && !terminal && decisions < maximum && operation != "CLOSE" && request.at("company_id") != expected_company) {
                response.update({{"status", "REJECTED"}, {"reason", "COMPANY_TURN"}});
            } else {
            _current_company = CompanyID{request.at("company_id").get<uint8_t>()};
            const CompanyID identity = _current_company;
            if (operation == "OBSERVE" && request.size() == 3) {
                response["observation"] = DevObservation(enumeration, decisions, maximum, ticks, pending, terminal, schema);
            } else if (operation == "TENSORS" && request.size() == 3) {
                if (pending || terminal) {
                    response.update({{"status", "REJECTED"}, {"reason", "DECISION_BOUNDARY"}});
                } else {
                    const std::string token = NativeStateSha256();
                    const auto base = std::filesystem::path(artifact_directory);
                    const std::string prefix = shared ? fmt::format("tensors-{:06}-company-{}", decisions, identity.base()) : fmt::format("tensors-{:06}", decisions);
                    const auto observation_path = base / (prefix + "-observation.json");
                    const auto candidates_path = base / (prefix + "-candidates.json");
                    if (!std::filesystem::exists(observation_path)) {
                        // Historical M15 encoded seeds as observation features.
                        // Use literal zeros for every seed argument: the live
                        // policy receives no reset seed or private RNG state.
                        const std::string digest = DevWritePublicTensors(observation_path);
                        WriteRlV2CandidatesAndMaybeExecute(candidates_path.string(), "", "", digest, 0, 0, 0);
                    }
                    Require(token == NativeStateSha256(), "development tensor observation mutated native state");
                    response["tensors"] = {{"schema_version", "openttd-rl-development-v2-public-tensors-1"},
                        {"company_id", identity.base()},
                        {"observation", observation_path.string()}, {"candidates", candidates_path.string()},
                        {"token", token}, {"can_act", decisions < maximum}, {"seed_features", "redacted-to-zero"}};
                }
            } else if (operation == "ACT" && request.size() == 5 && request.contains("token") && request.contains("candidate")) {
                if (pending || terminal || decisions >= maximum) {
                    response.update({{"status", "REJECTED"}, {"reason", "DECISION_BOUNDARY"}});
                } else if (request.at("token") != NativeStateSha256()) {
                    response.update({{"status", "REJECTED"}, {"reason", "STALE_TOKEN"}});
                } else {
                    // Re-enumerate native predicates before execution; callers
                    // cannot invent a command or use an unexposed candidate.
                    enumeration = EnumerateCandidates();
                    std::optional<Candidate> selected;
                    for (const auto &family : enumeration.selected) for (const Candidate &candidate : family) {
                        if (request.at("candidate") == candidate.stable_key) selected = candidate;
                    }
                    if (!selected) {
                        response.update({{"status", "REJECTED"}, {"reason", "ILLEGAL_CANDIDATE"}});
                    } else {
                        before = DevCompanyEconomy(); before_hash = NativeStateSha256();
                        action = ExecuteCandidate(*selected);
                        action["family"] = FAMILY_NAMES[static_cast<size_t>(selected->family)];
                        action["candidate"] = selected->stable_key; action["parameters"] = selected->parameters;
                        pending = true;
                        response["action"] = action;
                    }
                }
            } else if (operation == "STEP" && request.size() == 3) {
                if (!pending) {
                    response.update({{"status", "REJECTED"}, {"reason", "NO_PENDING_ACTION"}});
                } else {
                    uint64_t tick_before = TimerGameTick::counter;
                    // StateGameLoop requires the local UI company on entry and
                    // restores it after its OWNER_NONE simulation scope. The
                    // actor company is only the command/observation context.
                    _current_company = _local_company;
                    for (uint32_t tick = 0; tick < ticks; ++tick) StateGameLoop();
                    _current_company = identity;
                    ++decisions; pending = false;
                    json after = DevCompanyEconomy();
                    terminal = !after.at("alive").get<bool>();
                    if (shared) for (uint32_t company = 0; company < companies; ++company)
                        terminal = terminal || !DevCompanyEconomy(CompanyID{static_cast<uint8_t>(company)}).at("alive").get<bool>();
                    const std::string state_after = Company::GetIfValid(identity) == nullptr ? "company-absent" : NativeStateSha256();
                    json transition = {{"decision", decisions}, {"company_id", identity.base()}, {"action", action},
                        {"before", before}, {"after", after}, {"state_before", before_hash}, {"state_after", state_after},
                        {"tick_before", tick_before}, {"tick_after", TimerGameTick::counter},
                        {"terminal", terminal}, {"truncated", !terminal && decisions >= maximum}};
                    json research = transition;
                    if (shared) {
                        // Full simultaneous accounting is researcher-only. It
                        // is retained in the trace, never sent to either actor.
                        research["research_economies"] = json::array();
                        for (uint32_t company = 0; company < companies; ++company)
                            research["research_economies"].push_back(DevCompanyEconomy(CompanyID{static_cast<uint8_t>(company)}));
                    }
                    trace << research.dump() << '\n'; trace.flush();
                    Require(static_cast<bool>(trace), "development live trace write failed");
                    response["transition"] = transition;
                }
            } else if (operation == "CLOSE" && request.size() == 3) {
                close = true;
            } else {
                response.update({{"status", "REJECTED"}, {"reason", "REQUEST_SHAPE_OR_OPERATION"}});
            }
            }
            if (shared) response["next_company"] = (first_company + decisions) % companies;
            response["tick"] = TimerGameTick::counter;
            DevWriteResponse(output, response);
            if (close) break;
        }
        final.update({{"decisions", decisions}, {"pending_step", pending}, {"economy", DevCompanyEconomy()},
            {"tick", TimerGameTick::counter}, {"terminal", terminal}, {"status", terminal || decisions >= maximum ? "COMPLETE" : "CLOSED"}});
        if (shared) {
            final["companies"] = json::array();
            for (uint32_t company = 0; company < companies; ++company)
                final["companies"].push_back({{"company_id", company}, {"economy", DevCompanyEconomy(CompanyID{static_cast<uint8_t>(company)})}});
        }
    } catch (const std::exception &error) {
        final.update({{"status", "FAILED"}, {"error", error.what()}, {"decisions", decisions}, {"pending_step", pending}});
        WriteCanonicalNew(std::filesystem::path(artifact_directory) / "live-result.json", final);
        throw;
    }
    WriteCanonicalNew(std::filesystem::path(artifact_directory) / "live-result.json", final);
}
} // namespace
