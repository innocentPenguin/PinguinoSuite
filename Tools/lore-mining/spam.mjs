// Spam / viewbot filter for lore mining. Same rules as WelcomeBack.IsSpamText / IsSpamLogin in PinguinoHost/HostWelcomeBack.cs.
// "Best viewers with viewers streamboo .org" accounts must never become lore, people cards, graph nodes or welcome-back targets.
const NORMAL_LINKS = /(https?:\/\/)?([a-z0-9-]+\.)*(twitch\.tv|youtube\.com|youtu\.be|discord\.gg|discord\.com|spotify\.com)\S*/gi; // normal chat links
const DOMAIN = /(https?:\/\/|www\.|\b[a-z0-9][a-z0-9-]{2,}\s?\.\s?(org|com|net|xyz|ru|shop|site|club|ly|cc)\b)/i;
const PROMO = /\b(viewers?|followers?|views|subs|promo|cheap|boost|streamboo|bigfollows)\b/i;
const fold = t => t.normalize('NFKD').replace(/[̀-ͯ]/g, ''); // fancy-letter evasions fold to plain letters
export function isSpamText(text, firstMessage = false) {
  if (!text || !text.trim()) return false;
  text = fold(text);
  if (/best viewers with viewers/i.test(text)) return true;
  const t = text.replace(NORMAL_LINKS, ' ');
  return DOMAIN.test(t) && (firstMessage || PROMO.test(t));
}
export function isSpamLogin(login) {
  const l = String(login || '').toLowerCase().replace(/^@/, '').replace(/[^a-z0-9]/g, '');
  if (l.length < 16) return false;
  if (/[0-9][a-z][0-9]/.test(l.slice(-6))) return true;
  return /[bcdfghjklmnpqrstvwxz]{6,}$/.test(l);
}
/** rows: [{u, x, ...}] in time order. Spam ACCOUNT (all its rows dropped) = a viewbot-looking login or a FIRST message that is spam.
 *  Any other spam message (a regular whose account got hijacked) only drops that one row. Returns {users:Set, rows:[kept], droppedMessages}. */
export function filterSpam(rows) {
  const users = new Set(), seen = new Set(), bad = new Set();
  rows.forEach((r, i) => {
    const first = !seen.has(r.u); seen.add(r.u);
    if (isSpamLogin(r.u) || (first && isSpamText(r.x, true))) users.add(r.u);
    else if (isSpamText(r.x, false)) bad.add(i);
  });
  return { users, rows: rows.filter((r, i) => !users.has(r.u) && !bad.has(i)), droppedMessages: bad.size };
}
