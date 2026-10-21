# Boards UI: data shape the site expects (for 02 / Host)

Page: `/boards` (site, draft, local only). Reads `GET /api/boards?metric=<m>&period=<p>&key=<k>` (site proxies/stores what Host sends). Until it answers, the page shows demo data.

- metric: `watchtime` (value = minutes) | `points` | `messages` | `level` (value = level, optional `pct` = % to next level) | `gifts` | `bits`
- period: `day` | `week` | `month` | `year` | `all`
- key: day `YYYY-MM-DD`, week ISO `YYYY-Www`, month `YYYY-MM`, year `YYYY`, all `all` (America/Chicago, stream day). Empty key = current period.

```json
{
 "metric":"watchtime","period":"week","key":"2026-W43",
 "keys":["2026-W43","2026-W42","2026-W41"],
 "updatedAt":"2026-10-21T20:00:00Z","total":58,
 "rows":[{"rank":1,"login":"penguinfan","name":"PenguinFan","avatar":"https://...","value":1620}],
 "me":{"rank":15,"value":540}
}
```
- rows: top 10 only needed; `login` lowercase site login (links to /members/<login>); `avatar` optional https URL.
- keys: period keys that have data, newest first (feeds the "Look back" picker).
- total: number of ranked people (for "of N"). me: only when the caller is logged in (omit/null otherwise).
