/* Opt-in town-pair candidate focus. Included inside rl_v2_action.cpp's namespace.
 * The bounded candidate table ranks construction sites by distance to the most
 * populous town, so other towns' sites never become exposed and inter-town
 * routes cannot be built. With focus enabled, executing SELECT_TOWN_PAIR ranks
 * sites by distance to the segment joining the selected towns instead. The
 * selection is public adapter state: it is in the observation and the state
 * token, and saved games do not carry it. Without the opt-in nothing changes. */
static bool _dev_route_focus = false;
static std::optional<std::pair<TownID, TownID>> _dev_focus_towns;

static uint32_t DevAnchorDistance(TileIndex tile, const Town *anchor)
{
    if (_dev_route_focus && _dev_focus_towns) {
        const Town *first = Town::GetIfValid(_dev_focus_towns->first), *second = Town::GetIfValid(_dev_focus_towns->second);
        if (first != nullptr && second != nullptr) {
            // Manhattan distance to the nearest point of the segment between centres.
            const double ax = TileX(first->xy), ay = TileY(first->xy), bx = TileX(second->xy), by = TileY(second->xy);
            const double px = TileX(tile), py = TileY(tile), dx = bx - ax, dy = by - ay;
            const double length = dx * dx + dy * dy;
            const double t = length == 0 ? 0.0 : std::clamp(((px - ax) * dx + (py - ay) * dy) / length, 0.0, 1.0);
            return static_cast<uint32_t>(std::lround(std::abs(px - (ax + t * dx)) + std::abs(py - (ay + t * dy))));
        }
    }
    return anchor == nullptr ? Map::SizeX() + Map::SizeY() :
        static_cast<uint32_t>(std::abs(static_cast<int>(TileX(tile)) - static_cast<int>(TileX(anchor->xy))) +
        std::abs(static_cast<int>(TileY(tile)) - static_cast<int>(TileY(anchor->xy))));
}

static json DevFocusObservation()
{
    json towns = nullptr;
    if (_dev_focus_towns) towns = {_dev_focus_towns->first.base(), _dev_focus_towns->second.base()};
    return {{"mode", "town-pair-v1"}, {"towns", towns},
        {"ranking", "construction-sites-by-manhattan-distance-to-selected-town-segment"}};
}
