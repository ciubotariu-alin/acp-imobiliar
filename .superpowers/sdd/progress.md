# Progres — Plan 1: Schelet end-to-end ACP

Ramură: plan1-schelet-e2e
Plan: docs/superpowers/plans/2026-07-30-acp-schelet-end-to-end.md

## Task-uri
(în lucru)

Task 1: complete (commit df05966, review: 1 finding = plan/constraint wording conflict, resolved at plan level — commit-message language constraint relaxed to allow Romanian domain terms; no code change needed)
Task 2: complete (commit 0a69633, review clean)
Task 3: complete (commit 3a4dea7, review clean)
Task 4: complete (commit f6f9323, review approved; deviation method='inclusive' justified)
  - DEFERRED finding (Important, plan-mandated): dedup key include pretul → fragil pentru dupe reale cross-portal; de intarit in Plan 2 (dedup pe semnatura fizica + pret ca tie-breaker).
  - DEFERRED finding (Minor): inconsecventa quantile — statistica.py foloseste 'exclusive', filtrare.py 'inclusive'. q1/q3 nefolosite in Plan 1; de aliniat la 'inclusive' daca devin folosite.
  - DEFERRED finding (Minor): doua comparabile fara pret cu aceeasi supr/etaj/an colapseaza in dedup.
Task 5: complete (commit 8f7b443, review clean)
Task 6: complete (commits 1243246 + fix a604923, re-review approved; test gaps fixed)
  - DEFERRED (Minor): analizeaza ridica ValueError daca nicio comparabila n-are pret -> de tratat gratios in pipeline (Task 9) cu mesaj clar.
  - DEFERRED (Minor): parametrul 'chirii' e acceptat dar neutilizat inca (rezervat pentru randament, Plan 3).
  - DEFERRED (Minor): context calculat din comparabile nefiltrate (intentionat: oferta totala) - de confirmat.
Task 7: complete (commit 4db2f55, review clean)
Task 8: complete (commit a84a8be, review clean; PDF real 44KB produs)
  - ENV NOTE: WeasyPrint cere DYLD_LIBRARY_PATH=/opt/homebrew/lib la rulare (macOS). De documentat in README + SKILL (Task 10) si de folosit la demo (Task 9).
  - NOTE: crash-path "nicio comparabila cu pret" e deja acoperit de mesajul clar din calculeaza_statistici -> nu necesita guard suplimentar in pipeline.
Task 9: complete (commit c1e2ac7, review approved; PDF E2E 46KB produs; deviatie 'surse' corecta)
  - DEFERRED (Minor, in analiza.py din Task 6): 'surse' derivat din comparabile brute (pre-filtrare), deci o sursa ale carei comparabile au fost filtrate poate aparea totusi in surse. De revizuit in Plan 2/3.
Task 10: complete (commit 79f9a8b, review clean)

## Review final ramura (opus): Ready to merge YES (with 2 small fixes)
Fix final (commit 92baf65, re-review approved): #1 outlieri expusi in raport (transparenta spec); #2 param 'chirii' nefolosit sters. 26/26 teste, PDF regenerat.

## Deferred pentru Plan 2/3 (triaj review final):
- Literal/Enum pe marcaj/tip/incadrare/tensiune (evita mismatch la connectori reali)
- Field(gt=0) pe supr_totala (evita ZeroDivisionError)
- dedup: cheie fara pret + aliniere metoda quantile (statistica 'exclusive' vs filtrare 'inclusive')
- surse: split "consultate" vs "folosite" (deriva din set filtrat)
- logging in loc de print la connector cazut
- template: coloana dotari/parcare, marcaj 'vandut' vs 'listat', sufix _<data> in nume fisier + HTML intermediar

## STARE: Plan 1 COMPLET. 25->26 teste. PDF E2E functional.
