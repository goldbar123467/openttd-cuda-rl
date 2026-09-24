/* Opt-in live mail primitives. Included after the unchanged M15 executor.
 * No manufactured cargo, acceptance overrides, or fixture SERVICE calls. */
namespace {
static constexpr std::string_view DEV_CARGO_SCHEMA = "openttd-rl-development-v2-cargo-live-1";
static bool _dev_cargo_live = false;
static constexpr Family DEV_TRUCK_STOP = static_cast<Family>(12);
static constexpr Family DEV_MAIL_TRUCK = static_cast<Family>(13);

static Candidate DevMakeCargoCandidate(Family family, std::array<uint32_t, PARAMETER_WORDS> parameters, uint64_t priority, Money cost)
{
    Candidate candidate{family, parameters, {}, priority, cost, {}};
    candidate.parameters[0] = static_cast<uint8_t>(family);
    candidate.stable_key = CandidateKey(family, candidate.parameters);
    return candidate;
}

static bool DevTruckStop(const Candidate &candidate)
{
    return candidate.family == DEV_TRUCK_STOP;
}

static bool DevMailTruck(const Candidate &candidate)
{
    return candidate.family == DEV_MAIL_TRUCK;
}

static std::string_view DevCargoFamilyName(const Candidate &candidate)
{
    if (DevTruckStop(candidate)) return "BUILD_TRUCK_STOP";
    if (DevMailTruck(candidate)) return "BUY_MAIL_TRUCK";
    return FAMILY_NAMES[static_cast<size_t>(candidate.family)];
}

static CandidateEnumeration DevCargoCandidates()
{
    CandidateEnumeration result = EnumerateCandidates();
    if (!_dev_cargo_live) return result;
    // Keep the complete bus candidate set plus separately capped mail choices.
    // The internal buckets are not a neural tensor contract; cargo mode rejects
    // TENSORS until its new 14-family representation has been implemented.
    std::vector<Candidate> stops, purchases;
    const Town *anchor = nullptr;
    for (const Town *town : Town::Iterate()) if (anchor == nullptr ||
        std::tie(town->cache.population, anchor->index) > std::tie(anchor->cache.population, town->index)) anchor = town;
    for (TileIndex tile{}; tile < Map::Size(); ++tile) {
        uint32_t distance = anchor == nullptr ? Map::SizeX() + Map::SizeY() :
            static_cast<uint32_t>(std::abs(static_cast<int>(TileX(tile)) - static_cast<int>(TileX(anchor->xy))) +
                std::abs(static_cast<int>(TileY(tile)) - static_cast<int>(TileY(anchor->xy))));
        for (uint8_t direction = 0; direction < DIAGDIR_END; ++direction) {
            CommandCost cost = Command<CMD_BUILD_ROAD_STOP>::Do({}, tile, 1, 1, RoadStopType::Truck, false,
                static_cast<DiagDirection>(direction), ROADTYPE_ROAD, ROADSTOP_CLASS_DFLT, 0, NEW_STATION, false);
            if (cost.Failed()) continue;
            std::array<uint32_t, PARAMETER_WORDS> parameters{};
            parameters[1] = tile.base(); parameters[2] = direction; parameters[3] = 1;
            stops.push_back(DevMakeCargoCandidate(DEV_TRUCK_STOP, parameters,
                std::numeric_limits<uint32_t>::max() - distance, cost.GetCost()));
        }
    }
    const CargoType mail = GetCargoTypeByLabel(CT_MAIL);
    Require(IsValidCargoType(mail), "live mail cargo unavailable");
    for (const Depot *depot : Depot::Iterate()) {
        if (!IsRoadDepotTile(depot->xy) || GetTileOwner(depot->xy) != _current_company) continue;
        for (const Engine *engine : Engine::IterateType(VEH_ROAD)) {
            if (!engine->company_avail.Test(_current_company) || !engine->CanCarryCargo() ||
                !HasBit(GetUnionOfArticulatedRefitMasks(engine->index, true), mail)) continue;
            auto value = Command<CMD_BUILD_VEHICLE>::Do({}, depot->xy, engine->index, true, mail, INVALID_CLIENT_ID);
            const CommandCost &cost = std::get<0>(value);
            if (cost.Failed()) continue;
            std::array<uint32_t, PARAMETER_WORDS> parameters{};
            parameters[1] = depot->xy.base(); parameters[2] = engine->index.base(); parameters[3] = mail + 1;
            purchases.push_back(DevMakeCargoCandidate(DEV_MAIL_TRUCK, parameters,
                std::numeric_limits<uint32_t>::max() - depot->index.base(), cost.GetCost()));
        }
    }
    auto combine = [&](Family family, std::vector<Candidate> &extra) {
        const size_t index = static_cast<size_t>(family), limit = FAMILY_QUOTAS[index];
        auto &original = result.selected[index];
        result.total_legal[index] += extra.size();
        std::sort(extra.begin(), extra.end(), CandidateIsBetter);
        extra.resize(std::min(extra.size(), limit));
        original.insert(original.end(), extra.begin(), extra.end());
    };
    combine(Family::BuildBusStop, stops); combine(Family::BuyBus, purchases);
    return result;
}

static json DevCargoExecute(const Candidate &candidate)
{
    const auto &p = candidate.parameters;
    if (DevTruckStop(candidate)) {
        Require(_dev_cargo_live, "truck stop requires cargo schema");
        CommandCost cost = Command<CMD_BUILD_ROAD_STOP>::Do(DoCommandFlag::Execute, TileIndex{p[1]}, 1, 1,
            RoadStopType::Truck, false, static_cast<DiagDirection>(p[2]), ROADTYPE_ROAD, ROADSTOP_CLASS_DFLT, 0, NEW_STATION, false);
        return {{"native_commands", json::array({CommandLog("CMD_BUILD_ROAD_STOP", "EXECUTE", cost)})},
            {"rolled_back", false}, {"status", cost.Succeeded() ? "SUCCESS" : "NATIVE_REJECTED"}};
    }
    if (DevMailTruck(candidate)) {
        const CargoType mail = GetCargoTypeByLabel(CT_MAIL);
        Require(_dev_cargo_live && p[3] == static_cast<uint32_t>(mail) + 1, "mail purchase cargo differs");
        auto value = Command<CMD_BUILD_VEHICLE>::Do(DoCommandFlag::Execute, TileIndex{p[1]},
            EngineID{static_cast<uint16_t>(p[2])}, true, mail, INVALID_CLIENT_ID);
        const CommandCost &cost = std::get<0>(value);
        if (cost.Succeeded()) {
            const Vehicle *vehicle = Vehicle::Get(std::get<1>(value));
            Require(vehicle->owner == _current_company && vehicle->cargo_type == mail && vehicle->cargo_cap > 0,
                "native mail vehicle cargo/owner/capacity differs");
        }
        return {{"native_commands", json::array({CommandLog("CMD_BUILD_VEHICLE", "EXECUTE", cost)})},
            {"rolled_back", false}, {"status", cost.Succeeded() ? "SUCCESS" : "NATIVE_REJECTED"}};
    }
    return ExecuteCandidate(candidate);
}

static json DevCargoEconomy(json economy, CompanyID identity)
{
    if (!_dev_cargo_live || !Company::IsValidID(identity)) return economy;
    const CargoType mail = GetCargoTypeByLabel(CT_MAIL);
    const Company *company = Company::Get(identity);
    int64_t delivered = company->cur_economy.delivered_cargo[mail];
    for (uint8_t i = 0; i < company->num_valid_stat_ent; ++i) delivered += company->old_economy[i].delivered_cargo[mail];
    economy["delivered_mail"] = delivered;
    return economy;
}

static json DevCargoObservation(json observation)
{
    if (!_dev_cargo_live) return observation;
    observation["action_schema_id"] = "v2-development-passenger-mail-action-1";
    observation["capabilities"] = {{"cargo_labels", {"PASS", "MAIL"}}, {"neural_tensors", false},
        {"added_families", {"BUILD_TRUCK_STOP", "BUY_MAIL_TRUCK"}}, {"company_count", 1},
        {"station_facility_tiles", true},
        {"maximum_candidates", CANDIDATE_CAPACITY + FAMILY_QUOTAS[3] + FAMILY_QUOTAS[5]}};
    const CargoType mail = GetCargoTypeByLabel(CT_MAIL);
    const uint catchment = _settings_game.station.modified_catchment ? CA_TRUCK : CA_UNMODIFIED;
    observation["map"]["truck_stop_catchment_radius"] = catchment;
    for (auto &station : observation["stations"]) {
        const Station *native = Station::Get(StationID{station.at("id").get<uint16_t>()});
        const GoodsEntry &goods = native->goods[mail];
        station["accepts_mail"] = goods.status.Test(GoodsEntry::State::Acceptance);
        station["waiting_mail"] = goods.AvailableCount(); station["mail_rating"] = goods.rating;
        station["bus_stop_tiles"] = json::array(); station["truck_stop_tiles"] = json::array();
        for (const RoadStop *stop = native->bus_stops; stop != nullptr; stop = stop->next)
            station["bus_stop_tiles"].push_back(stop->xy.base());
        for (const RoadStop *stop = native->truck_stops; stop != nullptr; stop = stop->next)
            station["truck_stop_tiles"].push_back(stop->xy.base());
    }
    for (auto &vehicle : observation["vehicles"]) {
        const Vehicle *native = Vehicle::Get(VehicleID{vehicle.at("id").get<uint32_t>()});
        vehicle["cargo_type"] = native->cargo_type;
        vehicle["cargo_label"] = native->cargo_type == mail ? "MAIL" : "PASS";
    }
    for (auto &candidate : observation["candidates"]) {
        // No old tensor features are advertised as a compatible mail encoder.
        candidate.erase("features");
        if (candidate.at("family") == "BUILD_TRUCK_STOP") {
            TileIndex tile{candidate.at("parameters").at(1).get<uint32_t>()};
            candidate["family_index"] = 12;
            candidate["mail_acceptance_eighths"] = GetAcceptanceAroundTiles(tile, 1, 1, catchment)[mail];
            candidate["mail_production"] = GetProductionAroundTiles(tile, 1, 1, catchment)[mail];
        } else if (candidate.at("family") == "BUY_MAIL_TRUCK") candidate["family_index"] = 13;
    }
    return observation;
}
} // namespace
