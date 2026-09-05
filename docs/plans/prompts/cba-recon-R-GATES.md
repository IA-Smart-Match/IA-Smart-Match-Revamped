<role>Read-only CBA recon agent — R-GATES.</role>
<mission>Report current repository behavior against `docs/product/cba-smart-match-customer-requirements.md` §§17, 20–21, and §25 preserve/gate/defer items. Make no code or documentation changes.</mission>

<customer_mapping>
- §17: preserve the R/Y/G discovery feed and rename Connector Dashboard.
- §20: prohibit internet speaker search, scraping, external event discovery, cold outreach, CRM acquisition, membership/dues, and large branding-only work.
- §21: CPP green/gold is optional and must not delay function.
- §25: remove membership/dues references, prohibit external discovery, and treat branding/rewards as P2.
</customer_mapping>

<constraints>
- Read files only; cite repository path and current one-based line range for every claim.
- Map every finding to §25 P0/P1/P2 where applicable.
- Flag every customer §20 scope conflict.
- Recommend exactly one disposition per finding: preserve | gate | build new | defer OQ.
- Preserve code/data where possible; recommend CBA composition and navigation gates, not destructive deletion.
- Customer §4 says rewards/points remain and §25 makes only refinements P2. Preserve truthful server-backed rewards; recommend a gate only for a specifically evidenced chapter-only, unfunded, incomplete, or fake-success surface. Do not recommend disabling the whole capability.
</constraints>

<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md
2. services/api/smartmatch_api/routers/rewards.py
3. python/smartmatch_domain/smartmatch_domain/rewards.py
4. python/smartmatch_domain/smartmatch_domain/pipeline.py
5. python/smartmatch_persistence/smartmatch_persistence/pipeline.py
6. apps/web/legacy-frontend/src/app/pages/Dashboard.tsx
7. apps/web/legacy-frontend/src/app/components/DiscoveryFeed.tsx
8. apps/web/legacy-frontend/src/app/components/PipelineFunnelTiles.tsx
9. apps/web/legacy-frontend/src/app/pages/Outreach.tsx
10. apps/web/legacy-frontend/src/app/pages/LandingPage.tsx
11. docs/decisions/g3-crawler-decision.md
12. services/worker/smartmatch_worker/paid_extraction.py
13. apps/web/legacy-frontend/src/components/CrawlerFeed.tsx
14. services/api/smartmatch_api/config.py
15. apps/web/DESIGN.md
</read_first>

<output_sections>
1. File inventory (path | one-line role)
2. Current behavior (bullet per capability)
3. Gap table (requirement | today | gap severity P0/P1/P2 | disposition)
4. Tests to add or extend (exact paths)
5. Suggested branch and implementation fence
6. Gate recommendation for anything CBA must hide or refuse
</output_sections>
