# Removes the compatibility links left in D:\PinguinoBot. Only run this AFTER Streamer.bot has the re-pasted C# files
# and the OBS browser sources point at D:\PinguinoSuite\PinguinoB0t\overlays\...
$old = 'D:\PinguinoBot'
foreach ($j in "$old\overlays", "$old\GPT\chat_logs", "$old\GPT\profiles", "$old\GPT\history") {
    if (Test-Path $j) { (Get-Item $j -Force).Delete() }   # junctions: removes only the link, never the data
}
foreach ($f in "$old\commands.json", "$old\GPT\lore.json", "$old\GPT\common-words.txt", "$old\GPT\updates.json", "$old\README-MOVED.txt") {
    if (Test-Path $f) { [System.IO.File]::Delete($f) }
}
foreach ($d in "$old\GPT", $old) {
    if ((Test-Path $d) -and -not (Get-ChildItem $d -Force)) { [System.IO.Directory]::Delete($d) }
}
Write-Host 'Legacy links removed.'
