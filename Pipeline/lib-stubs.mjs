// Roles for a profile the Pipeline creates only because Twitch says the person is a sub (no chat history yet): the months / streak / founder flag
// come from the Host's subscriber roster (Data\subs\subscribers_master.json, read only). Profiles that already exist are never passed through here.
export function stubRoles(master, login) {
  const m = master && master.users && master.users[String(login).toLowerCase()];
  if (!m || typeof m !== 'object') return {};
  const r = { subMonths: Number(m.tenure) > 0 ? Number(m.tenure) : 0, subStreak: Number(m.streak) > 0 ? Number(m.streak) : 0 };
  if (m.founder === true) r.founder = true;
  return r;
}
