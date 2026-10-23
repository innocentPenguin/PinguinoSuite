# Helper drafts (unanswered questions)

Made by `Tools/helper-drafts.py` from the nightly logs. A mod fills in `Answer:`, then moves the entry into `Docs/HELPER_PUBLIC.md` (or `HELPER_MOD.md`) as a `## Title` section; the nightly pack build picks it up. Nothing here is in the knowledge pack.

_No unanswered questions in the nightly logs._

<!-- SPANISH-DRAFTS -->
# Borradores en español (México) para el pack público

**Estado: borrador, NO publicado.** Necesita el OK de Ivan antes de pasarlo a `Docs/HELPER_PUBLIC.md`. Son las entradas públicas en inglés pasadas a español mexicano: mismos datos, nada nuevo. Los comandos (!join, !queue...) no se traducen. Nunca se menciona ninguna contraseña de lobby. Pendiente de implementación: el constructor del pack (`Tools/build-helper-pack.py`) hoy lee un solo idioma; hay que decidir si va con sufijo `(ES)` en el título o en un pack aparte. Este bloque se conserva cuando se vuelve a correr `Tools/helper-drafts.py`.

## Cómo unirte a los juegos con los viewers
Regístrate una vez con !register TuNombreEpic, luego escribe "añádeme a la cola" o usa !join cuando la cola esté abierta. Cuando te elijan, busca el nombre del lobby privado en Rocket League. !queue muestra la fila y !pos muestra tu lugar.

## Dónde encontrar todos los comandos
La lista completa de comandos del chat, con buscador, está en https://innocentpenguin.com/commands (también en https://innocentpenguin.com/help).

## Tablas de posiciones y perfiles
Quienes más regalan subs, más bits, más hablan y las rachas de asistencia, de siempre o por mes: https://innocentpenguin.com/leaderboards. Tu perfil y tus estadísticas: https://innocentpenguin.com/members.

## Emotes
Los emotes de 7TV del canal están en una lista con buscador: https://innocentpenguin.com/emotes. !emote muestra qué tanto se usa un emote.

## Strikes y reglas del chat
Sé amable, nada de spam ni de odio. Los mods dan strikes cuando se rompen las reglas y cada strike baja uno por día. Las reglas y las preguntas comunes están en https://innocentpenguin.com/faq.

## Dejar de recibir menciones de los bots
Escribe !unping para que los bots dejen de mencionarte y !forgetme para que el chatbot olvide lo que aprendió de ti.

## Recordatorios y comandos divertidos
!remindme 30m descansa un rato crea un recordatorio en el chat, !reminders los lista y !cancelreminder borra uno. !8ball le hace una pregunta de sí o no al pingüino.

## Pedir ayuda a una persona
Si el helper no sabe algo, pregunta en el chat y un mod o Ivan lo verá. El helper no puede banear, dar timeout ni cambiar ajustes.

## Horario del stream
Ivan transmite todos los días a las 5:00 PM hora del centro. Primero Rocket League con viewers por un par de horas y luego otros juegos (Minecraft los lunes, Fortnite los viernes, juegos de terror los sábados). El horario completo está en la pestaña Schedule del canal: https://twitch.tv/innocentpenguin_/schedule

## Entrar al servidor de Minecraft desde consola
Las consolas entran con Bedrock Connect. Los pasos están en su página oficial: https://github.com/Pugmatt/BedrockConnect y luego agrega la dirección del servidor y el puerto Bedrock que da !ip.

## Pedirle una acción al helper
El helper solo responde preguntas. No puede cambiar el título, banear, dar o quitar mod, liberar mensajes retenidos ni cambiar ajustes. Para eso, pídeselo a un mod en el chat.

## Salir de la cola
Escribe !leave para salirte de la cola y !pos para ver tu lugar.

## Tus puntos
Escribe !points para ver tus puntos. Las tablas de posiciones están en https://innocentpenguin.com/leaderboards.

## Jugadores que ya jugaron (el reciclador)
Los jugadores sin strike pueden quedarse en la cola y los vuelven a formar después de jugar. !queue muestra la fila.

## Los customs se cierran por inactividad
Una partida custom se cierra después de 15 minutos sin actividad.

## Salir de la rueda del torneo
Escribe !notme para salirte de la rueda. !leave es solo para la cola de customs y no toca la rueda.

## Comandos mal escritos
Si te equivocas por una letra en un comando, el helper entiende qué quisiste decir. Los comandos de información como !pos, !queue, !points o !rank se ejecutan solos. Con !join y !leave pregunta "¿Quisiste decir !join?" y espera tu sí.
