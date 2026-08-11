# Enqueue the 'Writing on the Wall' slice as harness tasks (repo's D1-D14 build order).
Set-Location "$PSScriptRoot\.."
py -3.12 -m harness add "GENESIS D1-2: verify Content/GENESIS folder structure + naming; import Downtown Alley pack; blockout 1 city block + penthouse" --priority 0 --risk low --budget 3
py -3.12 -m harness add "GENESIS D3-4: Fragment pickup system + DT_Fragments" --contract contracts/genesis/fragment_pickup.yaml --after 1 --priority 0 --budget 6
py -3.12 -m harness add "GENESIS D5-6: Flashback trigger + level streaming (Belshazzar)" --contract contracts/genesis/flashback_stream.yaml --after 2 --priority 0 --budget 6
py -3.12 -m harness add "GENESIS D7-8: Spirit Realm post-process toggle" --contract contracts/genesis/spirit_realm_toggle.yaml --after 3 --priority 1 --budget 5
py -3.12 -m harness add "GENESIS D11-12: surface footsteps per repo recipe" --contract contracts/genesis/footsteps.yaml --after 4 --priority 2 --risk low --budget 2
py -3.12 -m harness add "GENESIS: hostile playtest of the slice" --contract contracts/library/playtest_sim.yaml --after 5 --priority 2 --risk low --autonomy 6 --budget 2
py -3.12 -m harness status
