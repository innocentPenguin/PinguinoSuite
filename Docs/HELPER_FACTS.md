# HelperPinguino facts and wordings

HelperPinguino answers Minecraft, Discord and "how do I join" questions from `Data\runtime\helper_facts.json`.
The file is created on first use (seeded from what Nightbot and the other chatbots said in the chat logs of 2026-10-16) and **should be checked once**.

| Key | Meaning |
|---|---|
| McSmpIp | the 24/7 SMP server address (Java needs only this) |
| McHardcoreIp | the stream-only hardcore server |
| McBedrockPort / McHardcoreBedrockPort | the Bedrock ports (SMP 19132, hardcore 9216) |
| McRules | one short rules line |
| Discord | the invite link |
| Website | main site |

- **Website override:** every 10 minutes the helper reads `FactsUrl` (default `https://innocentpenguin.com/api/faq`, in `helper_settings.json`). The site serves `{"faq":[{"key","question","answer","url"}...]}` (05 owns it, data in the site repo `content/faq.json`); the helper uses the `minecraft_ip` entry (both IPs and both Bedrock ports are parsed from its text) and the `discord` entry. A flat `{"McSmpIp":"..."}` also works. A site value wins; a missing or failing endpoint is ignored.
- **Minecraft flow:** an "ip" or "minecraft" question with no edition makes the helper ask Java or Bedrock. Java gets the IP, Bedrock gets the IP and the port.
- **AI, then repeat:** the first `PhraseBankSize` (3) answers per question are worded by the AI from the facts (each is rejected unless it contains the exact IP, port or link), stored in `helper_phrases.json`, and from then on the stored wordings repeat with no AI call. Changing a fact clears that question's stored wordings.
- **Key words** that bring the helper in unprompted: how, join, ip, !discord, minecraft, lobby, code, password, register, queue.
