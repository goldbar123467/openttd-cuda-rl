/* Opt-in orders-v1 actions. Included inside rl_v2_action.cpp's namespace.
 * Three public parameter words retain the existing candidate architecture. */
static bool _dev_bus_orders = false;
static constexpr size_t DEV_MAX_BUS_ORDERS = 4;
static constexpr std::string_view DEV_ORDER_ACTION_SCHEMA = "v2-m15-bus-orders-action-v1";

static CommandDataBuffer DevOrderBytes(const Order &order)
{
    return EndianBufferWriter<CommandDataBuffer>::FromValue(order);
}

static bool DevSupportedOrder(const Order &order)
{
    const auto bytes = DevOrderBytes(order);
    return bytes.size() == 11 && order.IsType(OT_GOTO_STATION) &&
        (bytes[0] == 0x21 || bytes[0] == 0x61) &&
        bytes[4] == CARGO_NO_REFIT && bytes[9] == 0xFF && bytes[10] == 0xFF;
}

static bool DevSupportedVehicle(const Vehicle *vehicle)
{
    if (vehicle == nullptr || vehicle->owner != _current_company || vehicle->type != VEH_ROAD ||
        !vehicle->IsPrimaryVehicle() || vehicle->cargo_type != GetCargoTypeByLabel(CT_PASSENGERS) ||
        vehicle->IsOrderListShared() || vehicle->GetNumOrders() > DEV_MAX_BUS_ORDERS) return false;
    for (const Order &order : vehicle->Orders()) if (!DevSupportedOrder(order)) return false;
    return true;
}

static CommandCost DevBusOrderCommand(const std::array<uint32_t, PARAMETER_WORDS> &p, DoCommandFlags flags)
{
    const Vehicle *vehicle = Vehicle::GetIfValid(VehicleID{p[1]});
    if (!DevSupportedVehicle(vehicle)) return CMD_ERROR;
    for (size_t i = 4; i < p.size(); ++i) if (p[i] != 0) return CMD_ERROR;
    const uint8_t operation = p[2] & 0xFF;
    const VehicleOrderID index = (p[2] >> 8) & 0xFF;
    const uint8_t kind = (p[2] >> 16) & 0xFF, order_flags = p[2] >> 24;
    switch (operation) {
        case 1: {
            if (vehicle->GetNumOrders() >= DEV_MAX_BUS_ORDERS || index > vehicle->GetNumOrders() ||
                (kind != 0x21 && kind != 0x61) || order_flags != 0 || p[3] > UINT16_MAX) return CMD_ERROR;
            Order order{kind, order_flags, DestinationID{static_cast<uint16_t>(p[3])}};
            return Command<CMD_INSERT_ORDER>::Do(flags, vehicle->index, index, order);
        }
        case 2:
            if (index >= vehicle->GetNumOrders() || kind != MOF_LOAD || order_flags != 0 ||
                (p[3] != 0 && p[3] != 2 && p[3] != 3 && p[3] != 4)) return CMD_ERROR;
            return Command<CMD_MODIFY_ORDER>::Do(flags, vehicle->index, index, MOF_LOAD, static_cast<uint16_t>(p[3]));
        case 3: {
            const Vehicle *source = Vehicle::GetIfValid(VehicleID{p[3]});
            if (p[2] != 3 || source == vehicle || !DevSupportedVehicle(source) || source->GetNumOrders() == 0) return CMD_ERROR;
            return Command<CMD_CLONE_ORDER>::Do(flags, CO_COPY, vehicle->index, source->index);
        }
        case 4:
            // Upstream treats an out-of-range index as declone/delete-all.
            // This primitive must never silently acquire those semantics.
            if (index >= vehicle->GetNumOrders() || kind != 0 || order_flags != 0 || p[3] != 0) return CMD_ERROR;
            return Command<CMD_DELETE_ORDER>::Do(flags, vehicle->index, index);
        default: return CMD_ERROR;
    }
}

template <typename Add>
static void DevEnumerateBusOrders(const Vehicle *vehicle, const std::vector<const Station *> &stations, Add &add)
{
    if (!DevSupportedVehicle(vehicle)) return;
    auto offer = [&](uint32_t descriptor, uint32_t argument) {
        std::array<uint32_t, PARAMETER_WORDS> p{};
        p[1] = vehicle->index.base(); p[2] = descriptor; p[3] = argument;
        const CommandCost cost = DevBusOrderCommand(p, {});
        if (cost.Failed()) return;
        Candidate candidate = MakeCandidate(Family::SetRoute, p, std::numeric_limits<uint32_t>::max() - vehicle->index.base(), cost.GetCost());
        if (vehicle->tile != INVALID_TILE) SetTileFeatures(candidate, 14, vehicle->tile);
        add(std::move(candidate));
    };
    if (vehicle->GetNumOrders() < DEV_MAX_BUS_ORDERS) {
        for (uint32_t index = 0; index <= vehicle->GetNumOrders(); ++index)
            for (const Station *station : stations) for (uint32_t kind : {0x21U, 0x61U})
                offer(1U | (index << 8) | (kind << 16), station->index.base());
    }
    for (uint32_t index = 0; index < vehicle->GetNumOrders(); ++index) {
        for (uint32_t load : {0U, 2U, 3U, 4U}) offer(2U | (index << 8) | (MOF_LOAD << 16), load);
        offer(4U | (index << 8), 0);
    }
    for (const Vehicle *source : Vehicle::Iterate()) if (source != vehicle && DevSupportedVehicle(source) && source->GetNumOrders() != 0)
        offer(3U, source->index.base());
}

static json DevPublicOrders(const Vehicle &vehicle)
{
    json orders = json::array(); size_t index = 0;
    for (const Order &order : vehicle.Orders()) {
        const auto bytes = DevOrderBytes(order);
        orders.push_back({{"index", index++}, {"type", static_cast<uint8_t>(order.GetType())},
            {"raw_type", bytes[0]}, {"raw_flags", bytes[1]}, {"destination", order.GetDestination().base()},
            {"load_mode", static_cast<uint8_t>(order.GetLoadType())},
            {"unload_mode", static_cast<uint8_t>(order.GetUnloadType())},
            {"non_stop", order.GetNonStopType().base()},
            {"wait_time", bytes[5] | (static_cast<uint16_t>(bytes[6]) << 8)},
            {"travel_time", bytes[7] | (static_cast<uint16_t>(bytes[8]) << 8)}, {"serialized", bytes}});
    }
    return orders;
}

static void DevAddVehicleOrderState(json &entry, const Vehicle &vehicle)
{
    entry["orders"] = DevPublicOrders(vehicle);
    entry["order_count"] = vehicle.GetNumOrders();
    entry["current_real_order_index"] = vehicle.cur_real_order_index;
    entry["current_implicit_order_index"] = vehicle.cur_implicit_order_index;
    entry["current_order_type"] = static_cast<uint8_t>(vehicle.current_order.GetType());
    entry["current_order_destination"] = vehicle.current_order.GetDestination().base();
    entry["current_order_time"] = vehicle.current_order_time;
    entry["orders_shared"] = vehicle.IsOrderListShared();
}

static json DevOrderObservationDescription()
{
    return {{"mode", "orders-v1"}, {"maximum_orders", DEV_MAX_BUS_ORDERS}, {"structured_marker_index", 511},
        {"structured_marker_value", 1}, {"vehicle_columns", {
            {"13", "stopped"}, {"14", "cargo_count/65535"}, {"15", "cargo_capacity/65535"},
            {"16", "order_count/4"}, {"17", "current_real_order_index/255"},
            {"18", "current_implicit_order_index/255"}, {"19", "current_order_type/255"},
            {"20:36", "four-[raw_type-plus-256-times-raw_flags,destination,wait_time,travel_time]-blocks-divided-by-65535"},
            {"36", "current_order_destination/65535"}, {"37", "log1p-current_order_time/log1p-UINT32_MAX"},
            {"38", "orders_shared"}, {"39", "reserved-zero"}}},
        {"unsupported_state", "fail-closed-on-shared-more-than-four-or-noncanonical-station-orders"}};
}

static void DevWriteOrderTensorState(std::vector<uint8_t> &bytes)
{
    auto write = [&](size_t offset, float value) {
        Require(offset + 4 <= bytes.size() && std::isfinite(value), "invalid orders tensor value");
        const uint32_t word = std::bit_cast<uint32_t>(value);
        for (size_t i = 0; i < 4; ++i) bytes[offset + i] = static_cast<uint8_t>(word >> (8 * i));
    };
    write(511 * sizeof(float), 1.0F);
    std::vector<const Vehicle *> vehicles;
    for (const Vehicle *vehicle : Vehicle::Iterate()) vehicles.push_back(vehicle);
    std::sort(vehicles.begin(), vehicles.end(), [](const Vehicle *a, const Vehicle *b) {
        return std::tuple(a->owner == _current_company ? 0 : 1, a->index.base()) <
            std::tuple(b->owner == _current_company ? 0 : 1, b->index.base());
    });
    Require(vehicles.size() <= 1024, "orders-v1 vehicle tensor would truncate");
    for (size_t row = 0; row < vehicles.size(); ++row) {
        const Vehicle &vehicle = *vehicles[row];
        if (vehicle.owner != _current_company || vehicle.type != VEH_ROAD || !vehicle.IsPrimaryVehicle()) continue;
        Require(DevSupportedVehicle(&vehicle), "orders-v1 requires at most four independent canonical passenger station orders");
        auto field = [&](size_t column, float value) { write(1286927 + (row * 40 + column) * 4, value); };
        field(13, vehicle.vehstatus.Test(VehState::Stopped) ? 1.0F : 0.0F);
        field(14, vehicle.cargo.StoredCount() / 65535.0F); field(15, vehicle.cargo_cap / 65535.0F);
        field(16, vehicle.GetNumOrders() / 4.0F); field(17, vehicle.cur_real_order_index / 255.0F);
        field(18, vehicle.cur_implicit_order_index / 255.0F);
        field(19, static_cast<uint8_t>(vehicle.current_order.GetType()) / 255.0F);
        size_t index = 0;
        for (const Order &order : vehicle.Orders()) {
            const auto raw = DevOrderBytes(order); const size_t column = 20 + 4 * index++;
            field(column, (raw[0] | (static_cast<uint16_t>(raw[1]) << 8)) / 65535.0F);
            field(column + 1, order.GetDestination().base() / 65535.0F);
            field(column + 2, (raw[5] | (static_cast<uint16_t>(raw[6]) << 8)) / 65535.0F);
            field(column + 3, (raw[7] | (static_cast<uint16_t>(raw[8]) << 8)) / 65535.0F);
        }
        field(36, vehicle.current_order.GetDestination().base() / 65535.0F);
        field(37, static_cast<float>(std::log1p(static_cast<double>(vehicle.current_order_time)) / std::log1p(static_cast<double>(UINT32_MAX))));
        field(38, vehicle.IsOrderListShared() ? 1.0F : 0.0F);
    }
}
