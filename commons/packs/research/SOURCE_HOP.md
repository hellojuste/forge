<!-- kit-authored · pack: research · owner: commons/packs/research/SOURCE_HOP.md · the order in which an investigation walks sources -->
# Source-hop order (research pack)

Walk sources from the most authoritative and least transformed to the least, and stop a hop only when the claim is
settled by a primary source or the trail ends. Every hop is logged (query, source, date accessed, what it said), so the
custody of each fact can be replayed.

## The order
1. **Primary record** — the document, dataset, filing, court record, registry entry, code at a pinned commit, or the
   original post/screenshot with its own metadata. Capture it (archive copy + sha256) before quoting it.
2. **The author's own context** — the same author's other statements, the page's earlier versions (web archive), the
   repository history around the pinned commit.
3. **Independent primary corroboration** — a second primary source that did NOT derive from the first (different
   origin, different collection path). Two copies of one press release are one source.
4. **Expert secondary** — peer-reviewed work, official statistics notes, standards bodies; cite the exact passage.
5. **Reputable reporting** — named outlets with a correction policy; prefer the one that links its primary source.
6. **Aggregators, wikis, social reposts** — leads only. Never the citation for a claim; follow them back to 1–3.

## Rules
- **Cite the hop you reached, not the one you started from.** A claim found on a social repost and confirmed in a
  registry is cited to the registry.
- **Record absence.** If the trail ends at hop 5 or 6, the claim is reported as unsupported, with the hop log.
- **Chain of custody.** Every captured artefact has: URL, access date (UTC), capture path, sha256, and who captured it.
  A screenshot without its source URL and time is a lead, not evidence.
- **Independence check.** Before counting two sources as corroboration, trace both to their origin; shared origin = one vote.
- **Terms of service and law.** Collection goes through public interfaces only; a source that forbids automated
  collection is read by hand or not at all. Personal data is minimised to what the question needs.
- **Licence of what you keep.** Quoting for analysis is fine; republishing a non-commercial (CC BY-NC) source's text
  into a commercial deliverable is not (the nc-lane rule).
