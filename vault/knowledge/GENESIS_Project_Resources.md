# GENESIS — Project Resources & AI Context
Source: github.com/calebhomwe/genesis (your repo, ingested 2026-07-11). Workers read this
before every GENESIS task. Bootstrap re-syncs it: tools/bootstrap.ps1 clones the repo fresh.

## Ground rules (from the repo — every worker obeys these)
- Third Person Template. **Blueprint only, no C++.** Target: PC, 60fps.
- Nanite OFF for prototyping; Lumen ON for lighting.
- Folder structure rooted at `Content/GENESIS/` exactly as the repo defines
  (Blueprints/{Core,Character,Interact,UI,QuestSystem,SpiritRealm}, Characters/{Seeker,NPCs},
  Environment/{Modern,Ancient}, DataTables, Maps/{Modern,Ancient}, Audio, VFX, Materials, UI).
- Naming conventions are LAW: BP_, SM_, SK_, M_, MI_, T_, DT_, WA_, ABP_, SC_, ENUM_, TAG_
  (e.g. BP_SeekerCharacter, DT_Fragments, TAG_Spirit_Active). Mismatched names break references.

## Core data: the Fragment (game's central collectible)
DT_Fragments row struct FFragmentData:
FragmentID (FName, e.g. "Gen_1_1") · Book · Chapter · VerseStart/End · FullText (FText)
· FlashbackLevel (TSoftObjectPtr<UWorld>) · UnlockedAbility (FGameplayTag)
· CurrentState (ENUM_FragmentState: Lost/Found/Dormant/Active)

## Characters
- Seeker (player): TPT base; Walk/Sprint/Crouch/Mantle; camera pull-in on interaction;
  abilities granted by Fragments, none at start.
- Usurpers (enemies): Grunt (melee, patrol, noise detection) · Possessed (fast, glitchy,
  damage-resistant) · Vessel (boss; weakened only by a specific Fragment verse).
- Preservers (allies): Guide (intel/map) · Guardian (fights, safe zones) · Witness (triggers flashbacks).

## First playable slice: "The Writing on the Wall" (build ONLY this)
1 city block (Downtown Alley Pack) · 1 penthouse interior · 1 fragment pickup BP ·
1 flashback trigger (level streaming + screen fade) · 1 Belshazzar scene ·
1 Spirit Realm toggle (post-process) · 1 return event (writing spreads to exterior).

## Asset shortlist (repo's picks)
Downtown Alley Pack (Fab) — modern streets · Medieval Modular Walls — ancient scenes ·
Megascans via Fab — surfaces · Niagara examples — spirit VFX · Starter Footsteps + Kenney RPG
SFX (CC0) + Sonniss GDC — audio · Mutable/Meta customization — character variants.

## Footstep recipe (repo's exact logic)
Physical Materials (PM_Concrete/Marble/Dirt/Grass) on floor meshes → ABP_Seeker anim
notifies on foot-down → SC_Footstep_* cues with random pitch/volume → on notify, trace
down from foot bone, switch on surface material, play matching cue.

## 14-day build order (repo) — mapped to harness tasks by tools/seed_genesis.ps1
D1-2 template+folders+imports · D3-4 fragment pickup + DT · D5-6 flashback trigger ·
D7-8 spirit realm toggle · D9-10 wire the sequence · D11-12 audio pass · D13-14 polish+capture.

## CLAUDE PRIME merge note
The repo's autonomy rules (make assumptions, don't stop at planning, refactor proactively,
modular/data-driven, no spaghetti BP) are adopted — EXCEPT self-declared success: in this
harness, evaluators declare success, and evidence (screenshots/tests) is mandatory. The
repo's Ollama endpoint (localhost:11434) is supported; default local tier is LM Studio (:1234).
The repo's separate GTA-style open-world spec is parked as a later epic; the funded path is
the Writing-on-the-Wall slice first (the repo itself says: build ONLY this first).
