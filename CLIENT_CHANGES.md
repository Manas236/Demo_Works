# CLIENT_CHANGES — what the client asked for

> **This file owns:** the client-facing status of every change the client has
> asked for, and the open questions we are waiting on them to answer.
>
> **This file does not own:** engineering gaps we found ourselves (→
> [ABOUT.md §7](ABOUT.md)), the ordered work queue (→ [STATE.md](STATE.md)),
> the business reasoning (→ [DOMAIN.md](DOMAIN.md)), or anything architectural
> (→ [ABOUT.md](ABOUT.md)).
>
> Where an item appears here **and** in ABOUT.md §7, this file owns the
> client-facing status and links to §7 for the technical detail. It does not
> restate it. §7 is the list of defects *we* found; this is the list of things
> *they* asked for. An item can be on both, and the two entries answer
> different questions.

---

## 0. Standing rule — read this before you act on anything below

**This file is a status record. It is NOT a work queue.**

**Gated: new scope priced into Phase 2.** Nothing here that is Pending may be
started until quotation **MG/SF/2026-02** is signed by the client. That is a
commercial gate, not an engineering one, and it is not yours to reach a view on.

> ### ⚠ OVERRIDDEN — 14 August 2026, by Manas Gawde
>
> **The gate above was overridden, not lifted and not met.** Quotation
> **MG/SF/2026-02 was still unsigned** on 14 August 2026 when Phase 2 work
> began. Manas took the decision to proceed anyway and instructed that the
> override be recorded rather than the rule deleted.
>
> **The rule above still stands and is still the default.** It is written in
> the present tense because it is still the policy; this block is the record
> that it was consciously set aside on one occasion, by the person entitled to
> set it aside. It is not evidence that the gate never existed, and it is not a
> precedent that clears the next item.
>
> **What proceeded under the override:** item 8, the receipts ledger, built on
> 14 August 2026. Anything else Pending is **still gated** and still needs
> either the signature or its own recorded override.
>
> **This does not convert Pending work into no-charge work.** §0's exemption
> covers defect and reachability fixes against scope already sold under
> MG/SF/2026-01; it does not cover item 8, which is new scope priced into
> MG/SF/2026-02 and remains chargeable there. Starting it early changed **when**
> it was built, not **what it costs** or **who agreed to it**.
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, this work was done against an unsigned
> quotation.
>
> ---
>
> ### ⚠ EXTENDED — 15 August 2026, by Manas Gawde
>
> **A second and third item proceeded under this same override, and MG/SF/2026-02 was
> still unsigned on 15 August 2026.** This block is extended rather than
> rewritten: the 14 August decision above stands exactly as recorded, and this
> is a second occasion, not a restatement of the first.
>
> **What proceeded:** **item 3** — removing the certified amount / certified
> quantity section from RA bills, and building the draft / issued / cancelled
> lifecycle that replaces the edit lock certification was providing as a side
> effect.
> And **item 2** — Client-wise segregation, giving a top-level ledger and near-duplicate
> client detection.
>
> **Items 2 and 3 remain CHARGEABLE under MG/SF/2026-02.** Section 7 of that quotation
> prices item 3 at **Rs 4,000**, and item 2 is also chargeable. They are **not** a §0 no-charge exemption: §0 exempts defect
> and reachability fixes against scope already sold under MG/SF/2026-01, and
> these are neither. Building it early changed
> **when** it was built, not **what it costs** or **who agreed to it**.
>
> **The gate is not lifted.** Every still-Pending item — 4 and 5 — continues
> to need either the signature on MG/SF/2026-02 or its own recorded override,
> decided by the client-facing owner. Overrides are not a precedent and do
> not make a subsequent one automatic; an override remains a decision that is taken and
> recorded, never one an agent may take, infer, or extend.
>
> **The commercial risk is unchanged and is restated deliberately:** if
> MG/SF/2026-02 is never signed, items 8, 3, and 2 were built against an
> unsigned quotation.

> ### ⚠ OVERRIDE — 16 August 2026, by Manas Gawde
>
> **A new block, not an amendment.** The 14 August and 15 August blocks above
> stand exactly as written and nothing in them has been edited, reformatted or
> re-scoped. This is a third occasion, decided on its own date.
>
> **MG/SF/2026-02 was still unsigned on 16 August 2026**, and Manas took the
> decision to proceed anyway.
>
> **What proceeds under this override:** **item 5** — the Delivery Challan
> raised from a BOQ, built 16 August 2026.
>
> **It also, and deliberately, authorises item 4 — the draft PO, built on 15
> August 2026 with no recorded override of its own.** The EXTENDED block above
> names only items 3 and 2; item 4 shipped alongside them and was left standing
> outside any authorisation, and the note further down §0 recorded that rather
> than resolving it, because resolving it was the client-facing owner's
> decision and not an agent's. **That decision is taken here.** The date gap is
> named rather than papered over: item 4 was built on **15 August 2026** and
> authorised on **16 August 2026**, one day later. This is a fresh dated
> authorisation covering earlier work, not a retrospective edit to the 15
> August block — amending an override to cover work it does not mention is
> precisely the act §0's own rule forbids.
>
> **Neither item becomes no-charge work.** §0's exemption covers defect and
> reachability fixes against scope already sold under MG/SF/2026-01. **Items 4
> and 5 are new scope priced into MG/SF/2026-02 and remain chargeable there.**
> Building them early changed **when** they were built, not **what they cost**
> or **who agreed to them**.
>
> **The gate is not lifted.** It is still the default and it still stands.
> Overrides are not a precedent and do not make a subsequent one automatic; an
> override remains a decision that is taken and recorded, never one an agent
> may take, infer, or extend.
>
> **The commercial risk is the client's to carry and ours to have flagged, and
> it is restated deliberately:** if MG/SF/2026-02 is never signed, items 8, 3,
> 2, 4 and 5 were all built against an unsigned quotation.

> ### ⚠ AUTHORISATION — 16 August 2026, by Manas Gawde — BOQ → real purchase order
>
> **A new block, not an amendment.** Every block above stands exactly as
> written; none has been edited, reformatted or re-scoped. This is a fourth
> occasion, and it is a **different kind** of one from the three above it,
> which is why it is worded from scratch rather than extended onto the last.
>
> **What proceeds:** raising a **real purchase order from a BOQ**
> (`/purchase/from-boq/<id>`) and **converting a priced draft PO into one**
> (`/purchase/from-draft/<id>`), together with the `boq_id`, `project_id` and
> per-line `line_id` that `purchase.py` needed to carry them. Built 16 August
> 2026.
>
> #### ⚠ This work is NOT on the client's change list at all
>
> **It is not item 4, it is not item 5, and it is not any other numbered item
> in this file.** The client has not asked for it. Read §2's item 4 and item 5
> and you will find the draft PO and the delivery challan; you will not find
> this, because nobody outside this office has ever requested it. It was
> identified here — the operator wanted work raised from a schedule to land in
> the ordinary purchase order register, and ABOUT.md §7 had already recorded
> that real procurement cost has no path to a project — and it was built on
> that basis.
>
> That distinction is the whole reason this block exists rather than a line
> added to the one above. The three overrides above set aside a **commercial
> gate on scope the client had asked for and we had priced**. This one
> authorises scope that **has never been asked for and has never been priced**,
> which is a different decision with a different risk attached, and folding it
> into a block about items 4 and 5 would have quietly reclassified it as
> something the client is expecting.
>
> **MG/SF/2026-02 was still unsigned on 16 August 2026.** Manas took the
> decision to proceed anyway and instructed that it be recorded rather than the
> rule deleted, exactly as on 14, 15 and 16 August.
>
> #### ⚠ No charge has been agreed for this, and none may be assumed
>
> **It is not covered by MG/SF/2026-02**, because it is not in it — that
> quotation prices the numbered items in §2 and this is not one of them. **It
> is not a §0 no-charge exemption either**, because that exemption covers
> defect and reachability fixes against scope already sold under
> MG/SF/2026-01, and a purchase order raised from a bill of quantities is new
> capability rather than making sold capability work.
>
> So it sits in neither bucket: **built, unrequested, unpriced, and with no
> charge agreed by anybody.** Whether it is billed, folded into a later
> quotation, or given away is a commercial decision for the client-facing
> owner to take with the client, and it has not been taken. **No agent may
> record it as chargeable, as delivered-no-charge, or as covered by any
> existing quotation**, and no agent may raise it with the client — the
> conversation is Manas's to have.
>
> **The gate is not lifted and this is not a precedent.** It is still the
> default and it still stands. That work outside the change list was authorised
> once does not make the next piece of unrequested work authorised, and an
> override remains a decision that is taken and recorded, never one an agent
> may take, infer, or extend. If anything, this block is the stronger warning
> of the four: the three above it are about *timing*, and this one is about
> *scope*.
>
> **The commercial risk is the client's to carry and ours to have flagged:**
> if MG/SF/2026-02 is never signed, items 8, 3, 2, 4 and 5 were all built
> against an unsigned quotation — and this work was built against no quotation
> at all.
>
> **Where the technical record lives:** [ABOUT.md §2](ABOUT.md) for the routes
> and the `purchase.py → boqpick.py` edge, [ABOUT.md §7](ABOUT.md) for the
> project-cost gap it narrows and the part of it that stays open, and
> [tests/test_boq_to_po.py](tests/test_boq_to_po.py) for what is actually
> guaranteed.

> ### ⚠ SUPERSEDED IN PART — 23 August 2026, by Manas Gawde — the draft PO half only
>
> **A new block, not an amendment.** The 16 August AUTHORISATION block above
> stands exactly as written; nothing in it has been edited, reformatted or
> re-scoped. This block supersedes **one half** of it and leaves the other half
> standing, and the two halves must not be collapsed into each other.
>
> **What changed on the outside.** Quotation **MG/SF/2026-02** was **sent on
> 21 August 2026 and has been read by the client.** Its **section 3**, titled
> *"Built since MG/SF/2026-01 — at no charge"*, lists F.01 to F.05 as built,
> included in the handover, and not charged for. **F.05 is the draft PO
> conversion** — *"a draft purchase order becomes a purchase order without
> re-entering a single line"*, which is `/purchase/from-draft/<id>`.
>
> #### The draft PO → PO route: the 16 August prohibition is SPENT
>
> The 16 August block forbade any agent recording that work as
> delivered-no-charge or as covered by any quotation, and forbade any agent
> raising it with the client. **It was written to protect an option to charge,
> and that option has now been spent by the client-facing owner in the ordinary
> way** — by telling the client, in writing, that the work is built, is in the
> handover, and is not charged for.
>
> So for **`/purchase/from-draft/<id>` only**, the 16 August prohibition no
> longer binds. That route may now be recorded as **delivered at no charge**,
> because that is exactly what the client has been told. Recording anything else
> would put this file in conflict with a commercial document the client is
> holding — and the document he is holding wins.
>
> [CLIENT_CHANGES-2.md](CLIENT_CHANGES-2.md)'s *"Already built, not in Phase 3"*
> section states it that way, and is **correct**. It carries a pointer back to
> this block.
>
> #### The BOQ → PO route: the 16 August prohibition STANDS, in full
>
> **`/purchase/from-boq/<id>` appears nowhere in MG/SF/2026-02.** It is not in
> section 3, it is not in 3A, 3B or 3C, and there is no reference anywhere in
> that quotation to a purchase order raised directly from a BOQ. **The client has
> been told nothing about it.**
>
> It therefore remains exactly what the 16 August block says it is: **built,
> unrequested, unpriced, and with no charge agreed by anybody.** Every sentence
> of that block continues to bind for this route — no agent may record it as
> chargeable, as delivered-no-charge, or as covered by any existing quotation,
> and no agent may raise it with the client. That conversation is still Manas's
> to have, and it has not been had.
>
> **The two routes were authorised in one block and are resolved separately on
> purpose.** They shipped together, in one piece of work, on the same `boq_id` /
> `project_id` / per-line `line_id` foundation — which is precisely what makes
> them easy to collapse into one another, and precisely why collapsing them would
> give away the only one of the two that is still worth anything.
>
> #### The scope of this supersession, stated so it cannot be stretched
>
> **This block supersedes the 16 August prohibition for one route and for no
> other work.** It is not a general finding that a sent quotation spends every
> prohibition in this file, and it is not a finding about section 3 as a whole.
> **No agent may extend it** — not to the BOQ → PO route, not to items 8, 3, 2,
> 4 and 5 (which are **chargeable** under MG/SF/2026-02 and are untouched by
> this), and not to anything built later. A supersession is a decision the
> client-facing owner takes and records, exactly as an override is; it is never
> one an agent may take, infer, or extend.
>
> **The gate is not lifted and this is not a precedent.** MG/SF/2026-02 is
> **valid until 28 August 2026** and was still **unsigned** when it was sent.
> Section 3 disclosing work as already delivered at no charge does not sign the
> rest of that quotation and does not authorise a single Phase 3 item;
> [CLIENT_CHANGES-2.md](CLIENT_CHANGES-2.md) stays gated in full.

> ### ⚠ OVERRIDE — 26 August 2026, by Manas Gawde — Phase 3B, access control only
>
> **A new block, not an amendment.** Every block above stands exactly as
> written; none has been edited, reformatted or re-scoped. This is the sixth
> occasion and the **first that reaches into Phase 3**, which is why it is
> worded from scratch rather than extended onto the block above it.
>
> **MG/SF/2026-02 was still unsigned on 26 August 2026**, and is **valid until
> 28 August 2026** — two days after this decision. Manas took the decision to
> proceed anyway and instructed that it be recorded rather than the rule
> deleted, exactly as on 14, 15, 16 and 23 August.
>
> #### What proceeds
>
> **Phase 3B items B1, B2, B3, B4 and B5 only** — user accounts and login,
> permissions as named strings minted in code, the Owner / Admin split, the six
> client roles, and default-deny access control across all 72 endpoints. Built
> 26 August 2026 in `auth.py`.
>
> **B6 (approvals), B7 (unapproved documents are view-only) and B8 (file
> attachments) are NOT authorised by this block and were not built.** They are
> the rest of 3B and they remain gated in full. So does every item of 3A and 3C.
>
> #### Two deviations from CLIENT_CHANGES-2.md, taken deliberately
>
> Both were put to the client-facing owner as decisions before any code was
> written, and neither is an agent's reading of the spec.
>
> 1. **B5's two-stage rollout was collapsed into one.** B5 asks for audit mode —
>    log what would be refused, run it, then flip to enforce. This enforces from
>    the start. 3C's approvals cannot be built on an unenforced layer: "an
>    unapproved document may be viewed but not printed" is not a guarantee an
>    audit-mode hook makes, so building B6 and B7 on one means re-verifying all
>    of it afterwards — and a second audit-mode pass needs a second override
>    cycle this calendar does not have. **The logging half of audit mode was
>    kept as a condition of the decision**: every refusal records the user, the
>    endpoint and the permission wanted, because the enumeration test proves no
>    endpoint is *unclassified* but cannot see one classified *too tight*.
>
> 2. **B3's Owner tier was built, and it is not in the six roles B4 names.**
>    B4 lists Director, Operations Head, HR, Sales Manager, Purchase Manager and
>    Accountant; B3 separately requires an Owner who defines what a role *means*
>    and an Admin who cannot. Seven roles ship, not six. Without the seventh the
>    client's own Directors could rewrite any role definition, which is the one
>    thing B3 says they may not do.
>
> #### It remains chargeable, and the price is unchanged
>
> **Phase 3B is priced in MG/SF/2026-02 and stays priced there.** This is not a
> §0 no-charge exemption: that exemption covers defect and reachability fixes
> against scope already sold under MG/SF/2026-01, and an access-control layer is
> new capability. Building it early changed **when** it was built, not **what it
> costs** or **who agreed to it**. No agent may record any part of 3B as
> delivered-no-charge or as covered by MG/SF/2026-01.
>
> **One thing inside this work is genuinely exempt and is recorded as such:**
> the `SECRET_KEY` demo default ([ABOUT.md §7](ABOUT.md) gap 8). That is a
> security defect in code already sold under MG/SF/2026-01, it is named in
> CLIENT_CHANGES-2.md's own "Security items promoted by this phase" as a narrow
> security fix rather than 3B scope, and it is closed by this work. The
> **unescaped output in `product.py` and `quotation.py`** named alongside it in
> that same section is **not** fixed and is still open.
>
> #### What was NOT built, and must not be assumed
>
> The five role lines the client stated at the 19 August meeting that carry **no
> 3A/3B/3C tag and appear nowhere in MG/SF/2026-02** — the two "visual
> dashboard" lines, HR editing salary, and the Accountant's employee overview
> and employee management — are **not** built and no permission stands in for
> any of them. CLIENT_CHANGES-2.md's own section says building them inside
> Phase 3 would be unpaid work; that is unchanged by this block.
>
> **CLIENT_CHANGES-2.md carries no per-role permission grid.** B4 names the
> roles and states exactly one restriction — HR information is kept from Sales,
> Purchase and Accounts. The permission set each of the seven roles ships with
> is therefore a **derived starting position, not a client instruction**, and it
> is editable by an Owner with checkboxes precisely so that it does not have to
> be right first time. It should be walked through with the client rather than
> presented as what he asked for.
>
> **The gate is not lifted and this is not a precedent.** It is still the
> default and it still stands. That Phase 3B was authorised does not authorise
> 3A, 3C, or the rest of 3B, and an override remains a decision that is taken
> and recorded, never one an agent may take, infer, or extend.
>
> **The commercial risk is the client's to carry and ours to have flagged, and
> it is restated deliberately:** if MG/SF/2026-02 is never signed, items 8, 3,
> 2, 4 and 5 **and the whole of the Phase 3B access-control layer** were built
> against an unsigned quotation — and MG/SF/2026-02 expires on 28 August 2026.
>
> **Where the technical record lives:** [ABOUT.md §2](ABOUT.md) for `auth.py`
> and its place in the import graph, [ABOUT.md §7](ABOUT.md) for the four gaps
> this work opens and the one it closes, [PROGRESS.md](PROGRESS.md) for the
> per-item build state, and
> [tests/test_access_control.py](tests/test_access_control.py) for what is
> actually guaranteed.

> ### ⚠ OVERRIDE — 27 August 2026, by Manas Gawde — Phase 3A, three document items only
>
> **A new block, not an amendment.** Every block above stands exactly as
> written; none has been edited, reformatted or re-scoped. This is the seventh
> occasion and the second that reaches into Phase 3.
>
> **MG/SF/2026-02 was still unsigned on 27 August 2026** and is **valid until
> 28 August 2026** — one day after this decision. Manas took the decision to
> proceed anyway and instructed that it be recorded rather than the rule
> deleted, exactly as on 14, 15, 16, 23 and 26 August.
>
> #### What proceeds
>
> **Phase 3A items A1, A2 and A5 only:**
>
> - **A1 — PO base rate editable.** The half that was missing: the rate on an
>   **existing** purchase order. Built as `GET,POST /purchase/edit/<id>` and
>   restricted to a PO in **Draft** status — see the deviation below.
> - **A2 — discount column on the final PO.** A per-line discount percentage,
>   inside the tax base.
> - **A5 — write-off / adjustment on a payment.** A `write_off` field on the
>   receipt record, feeding Total Outstanding on the client register.
>
> **A3 (additional charge lines) is NOT authorised by this block and was not
> built.** It is not gated for a commercial reason — it is stopped on an
> unanswered **tax** question that CC-2 does not settle and that no existing
> code path in this repo answers. See the deviation section below and
> [PROGRESS.md](PROGRESS.md) §6-H.
>
> **A4 and A6 were not built and are not authorised.** A4 was already BUILT and
> was only re-verified; A6 was already PARTIAL and was only re-reported. Neither
> gained a line of code under this block.
>
> #### Two deviations from CLIENT_CHANGES-2.md, taken deliberately
>
> 1. **A1 was narrowed to a Draft purchase order.** CC-2 calls A1 a
>    *"straightforward field unlock"* and carries no lifecycle qualification.
>    The code refuses more than that today for a stated reason:
>    `update_purchase()` is status-and-note only because *"a vendor has already
>    been told a price and a quantity, and changing them behind the document is
>    how a dispute starts."* `PO_STATUSES[0]` is **`Draft` — "written, not yet
>    sent to the vendor"** — so a Draft PO is precisely the case that reasoning
>    does **not** cover, and unlocking the rate there contradicts nothing.
>    Unlocking it on an **Issued** order would.
>
>    **This narrowing is the same shape as A6's and must be explained to the
>    client rather than silently applied.** Whether A1-as-sold covers editing
>    the rate on an issued PO is a commercial question and has not been asked.
>
> 2. **A3 was stopped rather than built, on a tax question.** A loading,
>    unloading or transportation line on a **buy-side** purchase order is either
>    part of the vendor's own consideration — s.15(2)(c) CGST Act, incidental
>    expenses, **inside** the taxable value — or a third-party cost we carry
>    ourselves, **outside** this vendor's supply altogether. CC-2 specifies the
>    repeater as *"label + amount"*, which carries no taxability, and the same
>    head is taxable on one order and not on the next depending on who performs
>    the work. There is no existing code path to read it off: no document in
>    this application carries a freight, packing or round-off line today, and
>    `charge.py`'s heads serve an expenses ledger that computes no tax at all.
>
>    An inflated taxable value on a purchase order overstates the input tax
>    credit we tell a vendor to bill us for, and their invoice then does not
>    reconcile. **That is not a defect testing finds**, so the item is stopped
>    and the question is put rather than answered.
>
> #### It remains chargeable, and the price is unchanged
>
> **Phase 3A is priced in MG/SF/2026-02 and stays priced there.** This is not a
> §0 no-charge exemption: that exemption covers defect and reachability fixes
> against scope already sold under MG/SF/2026-01, and all three of these are new
> capability. Building them early changed **when** they were built, not **what
> they cost** or **who agreed to them**. No agent may record any part of 3A as
> delivered-no-charge or as covered by MG/SF/2026-01.
>
> #### One pre-existing defect is named here and was NOT fixed
>
> `client.received_val` sums every receipt **regardless of mode**
> ([client.py:112](client.py#L112)), so the `mode="adjustment"` receipt that was
> the only way to clear a short-allowed balance before A5 makes Outstanding
> right by making **Received** wrong. A5's `write_off` field is a **separate**
> field from `amount` precisely so that new write-offs do not go through that
> path — but **adjustment-mode receipts already in the database are untouched**,
> and deciding what happens to them is a data question about live records, not
> a code question. It is reported in [PROGRESS.md](PROGRESS.md) §6-D and stays
> open.
>
> **The gate is not lifted and this is not a precedent.** It is still the
> default and it still stands. That A1, A2 and A5 were authorised does not
> authorise A3, the rest of 3A, the rest of 3B, or any of 3C, and an override
> remains a decision that is taken and recorded, never one an agent may take,
> infer, or extend.
>
> **The commercial risk is the client's to carry and ours to have flagged, and
> it is restated deliberately:** if MG/SF/2026-02 is never signed, items 8, 3,
> 2, 4 and 5, the whole of the Phase 3B access-control layer **and these three
> Phase 3A items** were built against an unsigned quotation — and MG/SF/2026-02
> expires **tomorrow**, on 28 August 2026.
>
> **Where the technical record lives:** [ABOUT.md §2](ABOUT.md) for the
> `/purchase/edit/<id>` route and the discount field, [ABOUT.md §7](ABOUT.md)
> for the gap A5 narrows and the one it leaves open,
> [PROGRESS.md](PROGRESS.md) for the per-item build state, and
> [tests/test_po_discount.py](tests/test_po_discount.py),
> [tests/test_po_rate_edit.py](tests/test_po_rate_edit.py) and
> [tests/test_receipt_write_off.py](tests/test_receipt_write_off.py) for what is
> actually guaranteed.

> ### ⚠ OVERRIDE — 28 August 2026, by Manas Gawde — A1's widening, A3 and A6
>
> **A new block, not an amendment.** Every block above stands exactly as
> written; none has been edited, reformatted or re-scoped. This is the eighth
> occasion and the third that reaches into Phase 3.
>
> **MG/SF/2026-02 is unsigned and expires TODAY, 28 August 2026.** Manas took
> the decision to proceed anyway and instructed that it be recorded rather than
> the rule deleted, exactly as on 14, 15, 16, 23, 26 and 27 August. This is the
> last day on which that decision can be taken against this quotation at all.
>
> #### What proceeds
>
> Three things, and each of them **answers a question an earlier block
> deliberately left open** rather than starting fresh scope:
>
> - **A1 — the Draft-only narrowing is LIFTED.** The 27 August block recorded
>   the narrowing as a deviation and said in terms that *"whether A1-as-sold
>   covers editing the rate on an issued PO is a commercial question and has not
>   been asked."* It is answered here: **repricing is allowed on a live purchase
>   order in any status, and every reprice is recorded** — who, when, and the
>   old rate → new rate on each line that moved — with that history shown on the
>   order. The reasoning is that the reason anyone wants an editable base rate is
>   that a wrong rate has **already gone out**; a restriction to Drafts leaves
>   exactly that case unsolved, which removes the feature's purpose. The
>   objection the narrowing protected — *"a vendor has already been told a
>   price"* — is answered by **recording** the change rather than forbidding it.
>
> - **A3 — additional charge lines on the final PO, AUTHORISED, and the tax
>   question is ANSWERED.** The 27 August block explicitly refused A3 and stopped
>   it on one sentence. The ruling is: **the charge is inside the taxable
>   value.** A line on a purchase order **we issue to a named vendor** is part of
>   what we are agreeing to pay **that vendor**, which is consideration for that
>   vendor's supply — s.15(2)(c) CGST Act, incidental expenses, **inside** the
>   taxable value. The third-party reading in the 27 August block describes a
>   cost that would **not appear on this vendor's PO at all**; it would be a
>   separate transaction with a separate party on a separate document. The
>   ambiguity is real in the world and is not real on this document.
>
>   **The exception is nonetheless made expressible rather than argued away.**
>   Each charge line carries a **taxable flag defaulting to true**, so the day a
>   genuine third-party freight cost has to sit on this order it can be marked
>   outside the base without another pass and without the tax-base question
>   being reopened under time pressure.
>
> - **A6 — the latest-bill-only restriction STAYS, and A6 closes as built with a
>   stated limitation.** RA bills are cumulative; editing bill 3 while bill 5
>   exists corrupts every claim downstream of it. The client asked without
>   qualification because the chain arithmetic is not his to know.
>   `claim_is_frozen()` → `is_latest_bill()` is **correct behaviour, not a
>   shortfall**. What proceeds is not a lifting: it is the refusal being made to
>   **explain itself and name the supported route** (cancel forward), and the
>   limitation being recorded in client-readable language. **Not one line of
>   `ra.py`'s lifecycle logic changes.** If the client wants arbitrary-bill
>   editing after hearing this, that is **new scope** and is not priced anywhere.
>
> #### One data decision is taken here, and it is the one §6-D was holding
>
> The 27 August block named `client.received_val` summing every receipt
> regardless of mode, and left it open because *"deciding what happens to them
> is a data question about live records, not a code question."*
>
> **The live database was queried before the decision was taken: there are ZERO
> adjustment-mode receipts in it** (1 receipt in total, mode `neft`). So the
> question had no live records behind it at all, and **no historical figure
> anybody has been shown moves by a rupee.** Adjustment-mode receipts are now
> kept out of **Received**, which is a bank-movement column, and are subtracted
> from **Outstanding** under their own name — see the deviation below for why
> they are not simply dropped.
>
> #### Three deviations, taken deliberately and recorded rather than applied
>
> 1. **A3 ships as a four-slot repeater with free-text labels, not four
>    hardcoded fields — and not the `/settings`-seeded head list either.**
>    CC-2's A3 note says *"do not build four fields"* and asks for one repeater
>    with the heads seeded in `/settings`. The instruction for this pass named
>    four lines — loading & unloading, transportation, and two further. **Both
>    are satisfied by the repeater**: it stores a list, every label is free text,
>    the first two slots are seeded with the client's own two heads, and the slot
>    count is one constant. What is **not** built is the `/settings`-editable head
>    list, because reading it would add a `purchase.py → settings.py` import edge
>    for a picker whose labels are already free text. **Recorded as a deviation
>    for the client-facing owner to confirm, not as delivered.**
>
> 2. **Adjustment-mode receipts are excluded from Received but NOT from
>    Outstanding.** The literal instruction for this pass was
>    `outstanding = billed − received − written_off` with `received`
>    payment-only, which would put every adjustment back into Outstanding.
>    **Two facts in the repo say that is wrong**: `ra.py`'s own note on
>    `RECEIPT_MODES` says an adjustment is settled against the bill and *"the
>    money genuinely stops being outstanding"*, and the §6-D tripwire asserts in
>    as many words that today's `total_outstanding == 0.0` is **right** and only
>    Received is wrong. So the fix follows A5's own precedent — *a separate
>    field rather than a figure folded into another* — and adds an **Adjusted**
>    term: Received is bank movements only, Outstanding is unchanged in every
>    case, and the register's columns reconcile. **This is a deviation from the
>    instruction and is flagged as one.**
>
> 3. **The Director-cannot-administer-an-Owner narrowing from 27 August
>    stands, and is recorded as a deliberate deviation from B3.** B3 says an
>    Admin may create, deactivate and assign roles; the code refuses that against
>    an **Owner** account. It is tighter than B3 because `_would_strand_install()`
>    only protects the **last** Owner, so spare Owners could be picked off one at
>    a time. **For the client to confirm, not a bug to fix.**
>
> #### It remains chargeable, and the price is unchanged
>
> **Phase 3A is priced in MG/SF/2026-02 and stays priced there.** This is not a
> §0 no-charge exemption: that exemption covers defect and reachability fixes
> against scope already sold under MG/SF/2026-01, and A3 is new capability.
> Building it early changed **when** it was built, not **what it costs** or
> **who agreed to it**. No agent may record any part of 3A as
> delivered-no-charge or as covered by MG/SF/2026-01.
>
> **Arbitrary-bill RA editing is NOT sold by A6 closing.** A6 closes as *built
> with a stated limitation*. Nobody may record the limitation as a defect owed
> to the client, and nobody may build past it without a fresh authorisation.
>
> **The gate is not lifted and this is not a precedent.** It is still the
> default and it still stands. That A1's widening, A3 and A6 were authorised
> does not authorise the rest of 3B or any of 3C, and an override remains a
> decision that is taken and recorded, never one an agent may take, infer, or
> extend.
>
> **The commercial risk is the client's to carry and ours to have flagged, and
> it is restated deliberately:** if MG/SF/2026-02 is never signed, items 8, 3,
> 2, 4 and 5, the whole of the Phase 3B access-control layer, the three Phase 3A
> items of 27 August **and these three** were built against an unsigned
> quotation — and MG/SF/2026-02 **expires today**.
>
> **Where the technical record lives:** [ABOUT.md §2](ABOUT.md) for the charge
> lines and the reprice log, [ABOUT.md §7](ABOUT.md) for the gap this closes and
> the ones it leaves open, [PROGRESS.md](PROGRESS.md) for the per-item build
> state, and [tests/test_po_charges.py](tests/test_po_charges.py),
> [tests/test_po_rate_edit.py](tests/test_po_rate_edit.py),
> [tests/test_ra_edit_delete.py](tests/test_ra_edit_delete.py) and
> [tests/test_receipt_write_off.py](tests/test_receipt_write_off.py) for what is
> actually guaranteed.

> ### ⚠ OVERRIDE — 29 August 2026, by Manas Gawde — extra PO lines (new scope) and C4
>
> **A new block, not an amendment.** Every block above stands exactly as
> written; none has been edited, reformatted or re-scoped. This is the ninth
> occasion and the fourth that reaches into Phase 3.
>
> #### ⚠ MG/SF/2026-02 EXPIRED on 28 August 2026, and the work below proceeds anyway
>
> **The quotation has lapsed.** It was sent on 21 August 2026, read by the
> client the same day, and **has never been answered** — no signature, no
> advance, no reply of any kind. The 28 August block above said in terms that it
> was *"the last day on which that decision can be taken against this quotation
> at all."* That day has passed. **Every override before this one was taken
> against a quotation that was unsigned; this is the first taken against one
> that is lapsed**, and the difference is recorded here rather than left to be
> discovered later by somebody reading this file and assuming the gate was met.
>
> Manas took the decision to proceed anyway, on 29 August 2026, and instructed
> that it be recorded rather than the rule deleted — exactly as on 14, 15, 16,
> 23, 26, 27 and 28 August. **A lapsed quotation is a stronger reason to record
> and a weaker reason to build**, and that tension is the point of this
> paragraph. Nothing below is evidence that the gate has been met or lifted.
>
> #### What proceeds — two things, and only these two
>
> - **Extra free-text purchase-order lines. ⚠ THIS IS NOT ONE OF CC-2's TWENTY
>   ITEMS.** The client asked, *after* the 19 August 2026 meeting that produced
>   that list, to be able to put parts on a purchase order that appear nowhere
>   on the BOQ, and sent a list of them carrying **no prices and no units**. It
>   has **no 3A/3B/3C tag**, it is **priced nowhere** — not in MG/SF/2026-02,
>   not in MG/SF/2026-01 — and it belongs in the same category as the five
>   lines in CLIENT_CHANGES-2.md's *"Stated by the client, NOT in
>   MG/SF/2026-02"* section. **No agent may record it as a Phase 3 item or
>   count it toward the twenty.** PROGRESS.md carries it in a section of its
>   own, outside the bars.
>
>   **The build shape was decided by the owner and is not an engineering choice
>   to revisit:** extra lines are **free text typed onto each order**. There is
>   no parts master, no catalogue collection, no picker and no per-vendor rate
>   table. A seeded price list exists **only as a typeahead prefill**, so that a
>   real order can be raised today; **every rate in it is an assumed placeholder
>   and none of it is a quoted or verified market price.** A line prefilled from
>   it is marked as assumed on screen, and that mark is **never printed** — the
>   vendor receives the order, not our note that we invented the price.
>
> - **C4 — employee master, AUTHORISED.** One of the seven NOT STARTED items,
>   gated until now. CC-2's C4 is *"Employee details and salary"* and that is
>   the whole of what proceeds: a register, a create form, a view, an edit and a
>   delete. **No attendance, no overtime, no salary calculation, and no link to
>   charges, projects or the P&L** — those are C5 and C6 and they stay gated.
>   The OT multiplier CC-2 requires to be a setting rather than a constant is
>   **not** pre-built either; laying groundwork for a gated item is starting it.
>
> #### What is NOT authorised and remains gated
>
> **B6, B7, B8, C1, C2 and C5**, and the two BLOCKED items **C3** and **C6**.
> Do not start any of them, do not lay groundwork for them, and do not add
> fields "ready for" them. That last clause is written down because it is the
> way this gate is most likely to be walked through by accident: a column added
> today for an item authorised next month is that item, started.
>
> #### Chargeability — and one half of it is genuinely unsettled
>
> **C4 is priced in MG/SF/2026-02 and stays priced there.** This is not a §0
> no-charge exemption: that exemption covers defect and reachability fixes
> against scope already sold under MG/SF/2026-01, and an employee master is new
> capability. Building it early changed **when** it was built, not **what it
> costs** or **who agreed to it**.
>
> ⚠ **The extra-lines work is priced NOWHERE, and no agent may invent a price
> for it or record it as delivered under either quotation.** It is not covered
> by MG/SF/2026-01 (it did not exist), and it is not covered by MG/SF/2026-02
> (it is untagged, and that quotation has in any case lapsed). Whether it is
> charged, absorbed, or folded into a replacement quotation is a **commercial
> decision the client-facing owner has not yet taken**. It is recorded here as
> unpriced so that the decision is visible when it is taken, rather than
> foreclosed by silence.
>
> #### The gate is not lifted and this is not a precedent
>
> It is still the default and it still stands. That extra PO lines and C4 were
> authorised does not authorise the rest of 3B or any of the remaining five 3C
> items, and an override remains a decision that is taken and recorded, never
> one an agent may take, infer, or extend.
>
> **The commercial risk is the client's to carry and ours to have flagged, and
> it is restated deliberately and in its sharpest form yet:** if MG/SF/2026-02
> is never signed, items 8, 3, 2, 4 and 5, the whole of the Phase 3B
> access-control layer, the three Phase 3A items of 27 August, the three of
> 28 August **and C4** were built against a quotation that has now **lapsed** —
> and the extra-lines work was built against **no quotation at all**.

> ### ⚠ OVERRIDE — 29 August 2026, by Manas Gawde — SECOND block of this date, after `86902ef`
>
> **A new block, not an amendment, and the second one dated 29 August 2026.**
> The block immediately above it — committed as `86902ef`, covering extra PO
> lines and C4 — **has not been edited, reformatted, re-scoped or extended by a
> single character.** It says what it said when it was written and it covers
> what it named. Amending an older block to cover work it does not mention is
> the specific act §0 forbids, and the item-4 note at the foot of this section
> is the standing record of what that mistake looks like. This is the tenth
> occasion overall and the fifth that reaches into Phase 3.
>
> **This block authorises no feature.** It closes findings the pass that
> produced `86902ef → 5605416` recorded against its own work. Nothing here
> starts a gated item, and nothing here moves the board.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated, not softened
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending", it is not "with the client", and it is not awaiting a countersign.
> **It is expired.** The block above was the first override taken against a
> lapsed quotation; this is the second, and the second is not evidence that the
> first made it routine. **A lapsed quotation is a stronger reason to record and
> a weaker reason to build**, and repeating the sentence is the point of it.
>
> #### What proceeds — one narrow unfreeze, and only this
>
> - **`quotation.py` is UNFROZEN NARROWLY, for ONE thing.** The freeze on that
>   file is **not lifted generally**. It is set aside for exactly one change:
>   **the deal panel's Committed figure**, which today re-derives its own total
>   from `STORE["purchases"]` instead of calling `purchase.job_cost()`. Two
>   functions computing the same commercial word is the defect; the missing
>   extra-line breakout row is a symptom of it. The unfreeze covers **that
>   figure and that breakout row and nothing else in that file.**
>
>   ⚠ **This block does not authorise a refactor, a rename, a tidy-up, or a
>   second edit.** Every other function in `quotation.py` stays frozen, and one
>   of them is frozen because a **stored XSS lived there**. Anything else that
>   looks wrong in that file is to be **noted and left**. If the change cannot
>   be made without touching a second function, the instruction is to **stop and
>   report**, not to widen this authorisation — an unfreeze that grows to fit
>   the work is not a narrow unfreeze.
>
>   ⚠ **Precondition, and it was met before a line was changed.** Every existing
>   quotation's committed figure was computed both ways against the live
>   database first, on the standing §6-D precedent that a change to a number
>   somebody may have quoted needs a count behind it. **A figure that moved was
>   to stop the work.** None moved. The measurement and its coverage — including
>   what the live data could *not* evidence — are recorded in the pass report and
>   in PROGRESS.md, honestly and including the part that is weak.
>
> #### The Operation Head ruling — REFUSED, and reversible by design
>
> **Operation Head is refused `employee.*`** — view, create, edit and delete —
> by the client-facing owner, on 29 August 2026. The role's seeded permission
> set does not grant it and does not gain it here.
>
> ⚠ **This is a REVERSIBLE DEFAULT, not a permanent policy, and the distinction
> is the whole of the ruling.** It is refused *for now*, on the narrow ground
> that it costs nothing to reverse: an Owner grants it at `/roles/edit/<id>`
> with four checkboxes, **no code change, no deployment, no developer and no
> re-login**. A default that is free to change is the right way to hold a
> question the client has not been asked. **Nobody may record this as the client
> having decided anything**, and nobody may cite it as precedent for refusing a
> role something else.
>
> ⚠ **CC-2 does not settle it, and the reason is narrower than "CC-2 is
> silent".** B4 *does* name Operations Head — it lists the six roles and that is
> one of them. What B4 says about employee data is a single sentence: *"HR
> information is restricted from Sales, Purchase and Accounts."* Operations Head
> is **not in that sentence**, in either direction: the specification neither
> grants it employee access nor withholds it. So the refusal is **ours**, and it
> must be marked in `docs/ACCESS_MATRIX.md` as **our derivation and not a
> specification** — marking it `§` would claim a backing that does not exist.
> The three roles B4 *does* name keep their `§`, because for them the sentence
> is real. CC-2 mentions Operations Head elsewhere (B6's approval ladder, and
> the untagged *"Operation Head — visual dashboard"* line among the five items
> that have no home); **none of those touches employee data either.**
>
> #### Still gated, untouched, and not started
>
> **B6, B7, B8, C1, C2 and C5**, and the two BLOCKED items **C3** and **C6**.
> Not one of them is started, and no groundwork is laid for any of them. No
> field is added "ready for" one, which remains the way this gate is most likely
> to be walked through by accident.
>
> #### Chargeability
>
> **Nothing in this block is new capability, so nothing in it is newly
> chargeable.** Closing a finding a pass raised against its own work is the §0
> **no-charge** exemption doing exactly what it is for. That does **not**
> retro-price the extra-lines work this pass hardens: **that remains priced
> nowhere** — not in MG/SF/2026-01, not in MG/SF/2026-02 — and whether it is
> charged, absorbed, or folded into a replacement quotation is still a
> commercial decision the client-facing owner **has not yet taken**.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. A narrow unfreeze of one file for one
> figure does not unfreeze that file, does not unfreeze `product.py`, and does
> not authorise the rest of 3B or any of the remaining 3C items. **An override
> is a decision the client-facing owner takes and records; it is never one an
> agent may take, infer, or extend** — and a *narrow* one is the easiest kind to
> extend by accident, which is why its scope is written twice above.

> ### ⚠ OVERRIDE — 29 August 2026, by Manas Gawde — THIRD block of this date: C5, the navigation re-baseline, and the alias cutback
>
> **A new block, not an amendment, and the third one dated 29 August 2026.**
> The two blocks above it — `86902ef` (extra PO lines and C4) and the one that
> followed `86902ef → 5605416` (the narrow `quotation.py` unfreeze and the
> Operation Head ruling) — **have not been edited, reformatted, re-scoped or
> extended by a single character.** Each says what it said when it was written
> and each covers what it named. Amending an older block to cover work it does
> not mention is the specific act §0 forbids, and the item-4 note at the foot of
> this section is the standing record of what that mistake looks like. This is
> the **eleventh occasion overall and the sixth that reaches into Phase 3**.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated a third time, not softened
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending", it is not "with the client", and it is not awaiting a countersign.
> **It is expired.** This is the **third** override taken against a lapsed
> quotation, and a third is not evidence that the first two made it routine.
> **A lapsed quotation is a stronger reason to record and a weaker reason to
> build**, and repeating the sentence is the point of it. Nothing below is
> evidence that the gate has been met or lifted.
>
> #### What proceeds — three things, and only these three
>
> - **C5 — attendance and site-wise labour cost, AUTHORISED.** One of the six
>   remaining NOT STARTED items, gated until now. CC-2's C5 is daily
>   presentee/absentee marking, **one employee = one site = one day**, overtime
>   at `salary ÷ 8 × hours`, and a site-wise labour cost figure. It consumes the
>   employee master C4 shipped and it is **a labour cost tracker, not payroll** —
>   PF, ESIC, professional tax and minimum wages remain the client's, per
>   MG/SF/2026-02 §5.
>
>   ⚠ **The OT multiplier is a SETTING and no literal multiplier may appear in
>   the calculation code.** CC-2 is explicit and the reason is not stylistic: the
>   client's own figure is 1× ordinary rate, statutory overtime under the
>   Factories Act and most state Shops & Establishments Acts is generally
>   **twice**, and hardcoding the client's figure would make this software
>   compute a **statutory underpayment**. It defaults to the client's figure and
>   lives at `/settings` with a line saying what it is and what it is not.
>
>   ⚠ **C5 is NOT to be wired into C6 or any P&L, and this authorisation does
>   not reach that far.** C6 is BLOCKED on the client's Open question 4 —
>   whether attendance-based wages or the BOQ installation base rate is
>   authoritative for labour cost — and subtracting both counts labour twice.
>   **C5 can be built without that answer; wiring it into C6 cannot.** Nothing
>   is exported, and `projectview.py`'s standing prohibition is untouched.
>
> - **The full navigation re-baseline, AUTHORISED — and every pinned print
>   golden will move.** `dashboard._nav()` is embedded in every printed page and
>   hidden by CSS at print, so a nav entry moves the pinned bytes of documents
>   whose printed appearance does not change by one character. That coupling is
>   [ABOUT.md §7](ABOUT.md)'s first gap and it is why the employee master shipped
>   with no link — a deliberate call to protect the goldens during an unattended
>   pass, which left the owner unable to find a page he had paid for.
>
>   **That call is now reversed on purpose. The movement of the goldens is the
>   intended outcome of this authorisation, not a side effect of it**, and the
>   re-baseline is the point rather than the price. Two conditions ride with it
>   and neither is negotiable: the movement in each document must be **confined
>   to the `_nav()` block**, every other block staying byte-identical; and **not
>   one figure, label or visible character on any printed sheet may change.** If
>   a nav change is visible on paper the print rule is wrong — **stop and
>   report, do not re-baseline.**
>
> - **The `po_parts.py` alias cutback, AUTHORISED as a DEFECT FIX.** The seeded
>   prefill table carries 73 canonical parts and 172 aliases, and the
>   overwhelming majority of those aliases are **invented — nobody wrote them**.
>   One class is a live wrong number: `200 mm elbow` and `200 mm elbow 8 inch`
>   are the same physical part reaching two different placeholder rates, so
>   which figure lands on a purchase order depends on how somebody typed it.
>   `_norm()`'s own docstring names that as the thing to avoid — *a match it
>   gets wrong puts a figure on a purchase order that nobody chose*.
>
>   **This is a defect fix against work delivered on 29 August 2026 and is a §0
>   no-charge item**, not new capability and not new scope. The rule it
>   establishes is that **an alias may exist only if the client wrote that exact
>   string, or it is a documented misspelling of a string the client wrote**;
>   everything else is deleted, and a test enforces the rule so the next pass
>   cannot reinvent them. **The test is the deliverable, not just the cutback.**
>
>   ⚠ **No canonical part may be merged or split.** `200mm elbow` and
>   `8" elbow` stay two separate entries with **no alias between them**, so
>   typing one can never fetch the other's rate. This block does **not** assert
>   they are the same part and does **not** assert they are different — that is a
>   parts question for the client, and the cutback removes the ambiguity rather
>   than answering it. It joins *is "PO red paint" red-oxide primer* as an open
>   question carried forward.
>
>   ⚠ **Prefill hit-rate falls, and the fall is correct.** `grinding wheel` will
>   no longer fill a rate: the line is accepted exactly as typed, with a blank
>   rate and no assumed flag, which is the honest outcome. A bare name that
>   silently chooses a size — the 4-inch wheel, the 20-litre thinner, the
>   non-Asian primer — is the same defect as the elbow, one step quieter.
>
> #### Still gated, untouched, and not started
>
> **B6, B7, B8, C1 and C2**, and the two BLOCKED items **C3** and **C6**. Not
> one of them is started, and no groundwork is laid for any of them. No field is
> added "ready for" one, which remains the way this gate is most likely to be
> walked through by accident.
>
> ⚠ **C2 in particular is NOT taken now, and the reason is recorded so it is not
> re-asked next pass.** C2 is the measurement document, and its approved
> quantity is what feeds RA-Installation — so **it needs an approval concept,
> and B6 does not exist.** Building C2 today means one of two things, and both
> are worse than waiting: a measurement document with **no approval step**,
> which defeats the document, since an unapproved measurement is a number
> somebody typed; or a **second approval concept** invented here that B6 must
> later reconcile with, which is how two ladders end up disagreeing about what
> "approved" means on the same record. **C2 follows B6.** C5 does not, which is
> why C5 is the item that moves.
>
> #### Chargeability
>
> **C5 is priced in MG/SF/2026-02 and stays priced there.** This is not a §0
> no-charge exemption: that exemption covers defect and reachability fixes
> against scope already sold under MG/SF/2026-01, and attendance and labour cost
> are new capability. Building it early changed **when** it was built, not
> **what it costs** or **who agreed to it** — and the quotation that prices it
> has lapsed.
>
> **The navigation re-baseline and the alias cutback are both no-charge.** The
> first makes a page already delivered actually reachable, which is the
> reachability half of the §0 exemption in its plainest form. The second is a
> defect fix against the extra-lines work of 29 August — and ⚠ **it does not
> retro-price that work, which remains priced NOWHERE**: not in MG/SF/2026-01,
> not in MG/SF/2026-02, and whether it is charged, absorbed, or folded into a
> replacement quotation is still a commercial decision the client-facing owner
> **has not yet taken**.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. That C5 was authorised does not
> authorise C1 or C2, and it emphatically does not open C6 — C6 is blocked on a
> question the client has not answered, and C5 arriving does not answer it.
> **An override is a decision the client-facing owner takes and records; it is
> never one an agent may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged, and
> it is restated in its sharpest form yet:** if MG/SF/2026-02 is never signed,
> items 8, 3, 2, 4 and 5, the whole of the Phase 3B access-control layer, the
> three Phase 3A items of 27 August, the three of 28 August, C4 **and now C5**
> were built against a quotation that has **lapsed** — and the extra-lines work,
> together with the cutback that now repairs it, was built against **no
> quotation at all**.

**Exempt: anything already sold under MG/SF/2026-01** — defect and reachability
fixes against scope already sold. Making something we have
already been paid for actually work is not new scope. Both are recorded here as
**Delivered — no charge**, and appear in MG/SF/2026-02 as already delivered.
Items 1 and 6 are both; wiring the BOQ revision chain was another.

**If you are an agent reading this file: a gated item that is not built is not a
task.** It is a record of a conversation. Do not open a file because you read
about one here, and do not treat a Pending row as a specification you have been
handed. If you think something gated should be built now, say so and stop.

That rule is unchanged by the overrides above. **An override is a decision the
client-facing owner takes and records; it is not one you may take, infer, or
extend.** Items 8, 3, 2, 4 and 5 being built early is not licence to start
anything else — and recorded overrides are not a precedent that makes a next
one automatic.

> ⚠ ~~**Item 4 is built and the override block does not name it.**~~ ✅
> **Resolved on 16 August 2026 by the block above**, which is a fresh dated
> authorisation covering it. The history is kept rather than deleted, because
> it is the reason the 16 August block is worded the way it is: the draft PO
> was delivered on **15 August 2026** alongside items 3 and 2, the EXTENDED
> block names only those two, and that block was left exactly as it stands —
> amending an override to cover work it does not mention is precisely the act
> the rule above forbids. So item 4 stood built with no recorded override for
> **one day**, and was authorised on its own date instead. Item 4's own entry
> carries the same note.

The queue lives in [STATE.md](STATE.md). This file feeds it; it is not it.

Phase 3 scope lives in [CLIENT_CHANGES-2.md](CLIENT_CHANGES-2.md). This file is
Phase 2 and earlier. The §0 rule above applies to that file in full.

---

## 1. How we approach this work

These are the standing decisions the items below are built against. They are
not restated per item.

### 1.1 The BOQ chain is deliberately separate from the sell chain

BOQ and RA bills are their own chain, parallel to quotation → proforma → tax
invoice, and they are separated **by import direction**, not by convention:

- `ra.py` may **not** import `invoice.py`. This is the load-bearing
  prohibition — the RA bill's tax block is per rate slab and carries HSN/SAC
  per claim row, while the sell chain's is document-level.
- `boq.py` may **not** import `ra.py` (nor `proforma.py`, `invoice.py`,
  `purchase.py`, `product.py`). The BOQ view page links out with `url_for` and
  reads `STORE["ra_bills"]` directly — the one-way trick.
- `quotation._tax_lines()` stays prohibited to `ra.py` for its own separate
  reasons ([INTRODUCTION.md §7](INTRODUCTION.md)).

[tests/test_import_directions.py](tests/test_import_directions.py) fails if any
of these is reversed. Full graph in [ABOUT.md §2b](ABOUT.md).

**Consequence for the items below:** every new document hung off a BOQ (draft
PO, delivery challan, proforma) is built **in the BOQ chain**, not by reaching
into the existing `/purchase`, `/proforma` or `/invoice` module. Where the
existing module already does a similar job, that is not a reason to import it.

### 1.2 Snapshot immutability — a printed document is driven by its own rows

A document that has been issued prints from **its own stored rows**. It is
never re-read from the live BOQ, and no figure on it is recomputed at render
time.

This is not a style preference. `print_ra()` was built as a loop over the live
`boq["line_items"]` and shipped green: a line deleted from the BOQ vanished
from the printed table while its amount stayed inside the printed Claim
Subtotal — an invoice whose rows did not add up to its own total.
[tests/test_ra_print_immutability.py](tests/test_ra_print_immutability.py) is
what now holds it. Detail in [ABOUT.md §5](ABOUT.md) (`/ra`).

**Every new document below inherits this rule**, and every new figure carried
across from another record — a previous balance, a certified amount, a
consignee — is **snapshotted at save**, never derived at print.

### 1.3 Anything hung off a BOQ gets its own collection

New documents get their own top-level collection in `STORE`. They are **not**
embedded as a list on the BOQ record.

The reason is `MAX_JSON_BYTES = 300,000`, the cap that actually binds on the
BOQ form: the client's real data shape reaches it at ~428 lines, below
`MAX_LINES`. Anything appended to the BOQ record eats that headroom and pushes
the failure into the schedule editor, where the user loses work that has
nothing to do with the thing that grew. See [ABOUT.md §5](ABOUT.md) (`/boq`).

### 1.4 `line_id` is the key; `item_no` is a display label

Every reference to a BOQ line — from a claim, a challan, a PO draft, anything
— matches on `line_id`. `item_no` is what a human reads and is editable,
duplicated in the client's own data, and renumbered by revisions.

A row carrying no `line_id` matches nothing and is skipped. It does **not**
fall back to `item_no`; a fallback would resurrect the exact collapse the key
exists to end, on precisely the ambiguous lines, and would do it silently.
[ABOUT.md §3](ABOUT.md) (RA Bill) carries the arithmetic this cost.

### 1.5 No tax head or place of supply gets guessed at

Nothing below adds a place-of-supply field, changes a `tax_type` default, or
encodes a derivation of which tax head applies. **That is pending the client's
CA.** ABOUT.md §7 gap 15 is the open technical record of it; §3 of this file
is the open client-facing question.

The rate-slab work that shipped deliberately stopped at the slab —
`ra._head_split()` splits a rate across whichever head the bill already
carries and decides nothing.

---

## 2. The change list — client meeting, 10 August 2026

| # | What they asked for | Status |
|---|---|---|
| 1 | Hide Base Rate and Escalation % from the printed BOQ | ✅ **Delivered — no charge** (§0 exempt) |
| 2 | Client-wise segregation — per-client totals and outstanding | ✅ **Delivered** — built 15 Aug 2026 under the §0 override; **chargeable under MG/SF/2026-02** |
| 3 | Remove the certified amount / certified qty section from RA bills | ✅ **Delivered** — built 15 Aug 2026 under the §0 override; **chargeable under MG/SF/2026-02** (Section 7, Rs 4,000) |
| 4 | Draft PO from a BOQ | ✅ **Delivered** — built 15 Aug 2026, authorised by the 16 Aug §0 override; **chargeable under MG/SF/2026-02** |
| 5 | Delivery Challan from a BOQ | ✅ **Delivered** — built 16 Aug 2026 under the §0 override; **chargeable under MG/SF/2026-02** |
| 6 | Raise RA1 from the BOQ | ✅ **Delivered — no charge** (§0 exempt) |
| 7 | Tax Invoice directly from the BOQ | ↩ **Answered differently** |
| 8 | Record payment received against an RA bill | ✅ **Delivered** — built 14 Aug 2026 under the §0 override; **chargeable under MG/SF/2026-02** |
| 9 | Employee / miscellaneous charges section | ✅ **Delivered** |
| 10 | Project folder grouping BOQs → net profit / loss | 🚧 Structure Built (Pass A), P&L Deferred |

---

### 1 · Hide Base Rate and Escalation % from the printed BOQ — ✅ Delivered, no charge

Both stay visible in the app; only the issued sheet drops them.

**Delivered under MG/SF/2026-01**, and carried into MG/SF/2026-02 as already
delivered — §0's exemption, at no charge.

**Approach.** `show_rate_breakup` is the single seam, and it defaults to
**False** — the issued document is what you get unless a caller opts in.
`GET /boq/print/<id>` passes False, `/boq/view/<id>` passes True, and the two
routes differ in that one argument and nothing else, so they can never quote
different money for one schedule. The flag gates four columns (base rate and
Esc. % on each of supply and installation); on the seeded schedule the
installation Esc. % is already hidden by `HIDE_EMPTY_ESCALATION`, so the
observed drop is **three columns per section**. The document header's
**Rate Basis** meta row is gated on the same flag — naming the basis on the
very sheet those figures were removed from hands back most of what was
withheld.

**Nothing was removed from storage.** All four fields are still captured,
still stored on every line, still persisted, and still what `_derived_rate`
suggests from.

→ [ABOUT.md §5](ABOUT.md), `/boq` — *"Base rate and escalation are
deliberately NOT on the issued print"*.

---

### 2 · Client-wise segregation — ✅ Delivered

`/client/` — every BOQ grouped by the party it is billed to, with schedule
value, issued, received and outstanding across all of it.

⚠ **Built on 15 August 2026 under the §0 override, with MG/SF/2026-02 still
unsigned.** New scope, **chargeable** under that quotation. See §0's override
block, which was extended rather than overwritten.

**It is a current-state screen, not a document**, so every figure is computed
live. Outstanding is **issued bills less receipts** — a draft has not been sent
and a cancelled one has been withdrawn, and putting either into a figure
somebody is about to chase a customer for would be a demand for money that was
never made or was explicitly retracted. It is not clamped at zero: an
overpayment shows as a credit.

**Near-duplicate names are reported and never merged.** The grouping key is
`pipeline.norm_name(account_name)` — casefolded, whitespace-collapsed,
**punctuation kept** — so `Pvt Ltd` and `Pvt. Ltd.` stay two groups with an
amber band naming them. There is no `customer_id` anywhere in this app; merging
them would be the system deciding two typed names are one party, which it
cannot know (DOMAIN.md §6).

**The minimal party-edit route** (`/client/edit-party/<id>`) writes the
customer block and nothing else — no line, no rate, no quantity, no section, no
project field. It is not the general BOQ edit and must not become one; a test
posts a full set of decoys to hold that.

⚠ **Two corrections to what was first delivered**, both made on 15 August 2026:

- **A GET on a locked schedule now renders the form READ-ONLY** rather than
  bouncing. It refused on GET as well as POST, so a locked BOQ's customer
  details could not even be *looked at* from that page. The controls are
  disabled, the blocking bills are named and linked, and the POST is what
  refuses.
- **The lock was narrowed to DRAFT and ISSUED bills.** It had counted bills of
  any status, and a cancelled bill can never be deleted or un-cancelled — so
  one of them froze that BOQ's customer name permanently with no escape, and
  that client then stayed split across two rows of this very page forever. A
  cancelled bill is excluded from every other total in this app by design.
  Where a bill's frozen party snapshot and the live schedule now disagree,
  `/ra/view` raises an amber band giving both and stating that the document is
  deliberately not restated — the same divergence surface the receipts work
  established, reused rather than rewritten.

⚠ **It inherits [ABOUT.md §7](ABOUT.md) gap 17.** `outstanding_of()` is
`grand_total − receipts` and `grand_total` is what we *claimed*; there is
nowhere to record that the main contractor allowed less. This page rolls that
figure up per client, which widens where the overstatement is visible without
changing its size. §3 below carries the question for them.

→ [ABOUT.md §5](ABOUT.md) (`/client`) for the pages;
[tests/test_client_segregation.py](tests/test_client_segregation.py),
[tests/test_norm_name.py](tests/test_norm_name.py).

---

### 3 · Remove the certified amount / certified qty section from RA bills — ✅ Delivered

Removed entirely, not hidden behind a flag.

⚠ **Built on 15 August 2026 under the §0 override, with MG/SF/2026-02 still
unsigned.** This is **new scope and remains chargeable** under that quotation —
**Section 7 prices it at Rs 4,000** as *"RA issue + cancellation with the
certified section removed"*. It is **not** a §0 no-charge exemption: §0 exempts
defect and reachability fixes against scope already sold under MG/SF/2026-01,
and certification was neither broken nor unreachable. See §0's override block,
which was extended rather than overwritten.

**What went.** The route `/ra/certify/<id>` and its page; `certified_qty` and
`certified_rate` on every claim row; `certified_on` and the old
`draft | submitted | certified` status on the bill; the certified quantity and
amount columns on `/ra/print`, `/ra/view` and the register, with the register's
*Total Certified Amount* tile and *Certification* badge column; and every helper
that computed or validated certification — nine functions in all. Nothing about
it survives in code.

**What replaced the LOCK, which is the part the ask did not mention.**
Certification was doing two unrelated jobs: it was the main contractor's ruling,
*and* it was the only thing stopping an already-submitted bill being edited or
deleted (`has_certification()` gated `can_delete()`, and the old `status` was
the flag). Removing the ruling removed the lock, so the lock is rebuilt as an
explicit lifecycle:

| State | What it permits |
|---|---|
| `draft` | editable, deletable subject to the existing receipts guard, prints with a **DRAFT** marker |
| `issued` | `edit_ra` and `delete_ra` both refuse; prints clean; money may be receipted against it |
| `cancelled` | locked, reason and date recorded, excluded from every total and from outstanding, **cannot be un-cancelled**, prints over a CANCELLED overprint |

**`ra_no` is never reused.** A cancelled RA3 stays RA3 and the next bill is RA4,
the same reasoning that stops a GST serial being reissued — the number has been
quoted in somebody else's ledger. `next_ra_no()` counts cancelled bills, which
makes that true by construction rather than by a rule somebody remembers.

**The over-claim guard now counts drafts and excludes cancelled bills.** Both
halves are load-bearing and neither is obvious: two drafts each claiming a
line's whole remaining balance are both caught, and cancelling a bill releases
its quantity back onto every line it claimed. `OVERCLAIM_TOLERANCE` is still
`0.0` and the control constants are untouched.

**Receipts.** A receipt may only be recorded against an **issued** bill
(`ra.can_receipt()`, stated once and read by both `receipt.py` and the control
on `/ra/view`), and cancelling a bill that carries receipts is **refused** in
the same shape as the existing `can_delete()` refusal.

**Routes** are `GET,POST /ra/issue/<id>` and `GET,POST /ra/cancel/<id>`,
following `9d060ee`'s shape exactly: the GET renders a confirmation page and
mutates nothing, the state change happens only in the POST branch, and there is
no browser `confirm()` anywhere. ABOUT.md §7.9f's `url_map` sweep only walks
rules whose path contains "delete", so **neither route is covered by it** and
each ships its own test asserting a GET changes no status.

**Data migration.** `tools/strip_certification.py` — one-shot, idempotent, not
wired into startup. Applied to the working database on 15 August 2026:
**2 bills, 6 certification keys across 2 claim rows**, both migrated from
`draft` to `issued`. Every existing bill becomes `issued` and none is left a
draft: the old `status` was a certification-tracking field with no gate attached
to it, so a stored `"draft"` said nothing about whether the bill was sent.

⚠ **What this cost, stated plainly:** any certified quantity or rate already
keyed in is destroyed and is recoverable only from the dated dump in
`backups/`. That is what "remove it entirely" means.

⚠ **And what it leaves open:** there is now **no way to record that the main
contractor allowed less than was claimed**, and no credit-note flow to correct
it, so outstanding is overstated for any bill certified down. New in
[ABOUT.md §7](ABOUT.md) gap 17.

→ [ABOUT.md §7](ABOUT.md) gaps 3, 9f and 17; [ABOUT.md §5](ABOUT.md) (`/ra`);
[tests/test_ra_routes.py](tests/test_ra_routes.py),
[tests/test_strip_certification.py](tests/test_strip_certification.py).

---

### 4 · Draft PO from a BOQ — ✅ Delivered

`/po/` — description and quantity only. **Rates blank. No supplier buy-rates on
it. No GST.**

⚠ **Built on 15 August 2026 under the §0 override, with MG/SF/2026-02 still
unsigned.** New scope, **chargeable** under that quotation.

> ⚠ ~~**A gap in the record, reported rather than papered over.**~~ ✅
> **Closed on 16 August 2026.** §0's override block, extended on 15 August
> 2026, names **items 3 and 2** as what proceeded and **does not name item 4**,
> which was built on the same day under the same circumstances. That block is
> still left exactly as it stands — amending an override to cover work it does
> not mention is not an agent's to make. Instead, the **16 August 2026 block**
> is a fresh dated authorisation that covers this item explicitly and names the
> one-day gap between building it and authorising it. It remains **chargeable**
> under MG/SF/2026-02, and if that quotation is never signed this work was done
> against an unsigned one.

**Built in the BOQ chain**, not by reusing `/purchase`. Two client constraints
made that necessary and both are hard: **one running PO number series** across
all suppliers and all sites, and **no GST**. The buy-side PO computes CGST /
SGST / IGST on every order and numbers through an FY-scoped series, and merging
them would put the no-GST rule onto a record that legitimately needs GST —
that PO records **input tax we pay**.

**Separate behaviour, shared appearance.** The document prints on the same A4
sheet as the buy-side PO — same letterhead, same party block, same table shell,
same signature — through the shared `docsheet.py`. It differs only where the
client asked: no GST block at all (not a zero-rated one), rates blank, and a
`Pcs` column beside `Qty`.

**Rates being blank is the point of the document, not an unfinished state.** It
goes to a supplier to be priced, and nothing on it reads a buy rate from
anywhere. The BOQ's own `supply_rate` is the dangerous one — that is what we
*sell* the work for, and printing it on the sheet handed to the person quoting
us is the worst thing this document could do. There is a test for it.

**The line picker.** `/po/create?boq=<id>` lists every BOQ line as a checkbox
row with an editable quantity defaulting to the schedule's, plus select-all and
clear-all. **Every box arrives ticked**, because most orders are the whole
schedule — but the operator can untick down to a few. Only ticked lines are
snapshotted; nothing ticked is **refused with a message**, never written as an
empty PO. A ticked size brings its specification clause with it, carrying no
quantity. Matching is on `line_id` (§1.4).

**Numbering.** The prefix and the next number are **editable at `/settings`**,
defaulting to `SF/DPO` and 1. They have to be: the client's series already
exists on paper, and a hardcoded start would collide with their book on the
first order. The counter is **global, deliberately not per-BOQ** — the opposite
of `ra_no`, which is per project because it is that job's own sequence. **A
deleted draft PO does not release its number.**

**The vendor** is a picker over the shared address book (`type: "vendor"`),
with a **free-text fallback** for a one-off supplier not worth an entry.
The brief specified free-text party fields; the address book is an improvement
on that — it carries the address and the GSTIN and cannot be spelled two ways —
so both are offered and whichever was used is snapshotted onto the PO at create.
It is **still not a vendor master**: [ABOUT.md §7](ABOUT.md) gap B6.

⚠ **Still worth confirming with the client:** "one running series" versus the FY
reset every other series in this app uses. A series that never resets and one
that resets each April are both "one series across all suppliers and sites",
and they produce different numbers. **What was built does not reset**, taking
the ask literally.

⚠ **Nothing captures the rates the supplier quotes back.** The priced copy comes
in on paper and is re-keyed into a buy-side PO, with no link between the two
documents. [ABOUT.md §7](ABOUT.md) gap B7.

→ [ABOUT.md §5](ABOUT.md) (`/po`) for the pages and (`/purchase`) for what the
existing PO is; [tests/test_po_draft.py](tests/test_po_draft.py).

---

### 5 · Delivery Challan from a BOQ — ✅ Delivered

`/dc/` — description, quantity and unit. **No rates, no amounts, no tax, no
totals and no bank block.** A challan that carries money is an invoice wearing
a different heading.

⚠ **Built on 16 August 2026 under the §0 override, with MG/SF/2026-02 still
unsigned.** New scope, **chargeable** under that quotation.

**Built to their own DC54**, which is the ground truth for the layout: the
title band inside the page border and above the letterhead, the two
two-column blocks (office against consignee, then challan meta against
dispatch meta), the **DESCRIPTION OF GOODS** band, and a four-column table —
Sr.No., Description, Qty, Unit — with nothing else in it.

**Built in the BOQ chain**, beside the RA bill and independently of it.
`challan.py` may not import `ra.py`: a challan records material dispatched and
an RA bill records money claimed, and they diverge in both directions on a real
site. Nothing reconciles them, which is recorded as [ABOUT.md §7](ABOUT.md)
gap 19 rather than solved here.

**The consignee is the SITE, not the party being billed.** On DC54 the
consignee is Samruddhi themselves at "Sify Infinit, Bangalore" — they are
moving their own material to their own store (DOMAIN.md §5.1). It defaults to
the company name from `/settings` and is **never** wired to the BOQ's
`account_name`, which is the main contractor. The fields are free text, with
the address book offered beside them as an **optional prefill** — the same
arrangement the draft PO's vendor block has, and for one more reason: a site
store that exists for four months is not worth an address-book entry.

**Numbering.** The prefix and the next number are editable at `/settings`, and
the prefix **defaults to blank**, because their series has none: challan 54 is
the bare integer `54`. So a blank prefix prints the number unpadded and the
series can be seeded to 55 to continue their book; set a prefix and it takes
the padded `PREFIX/0055` shape every other series here uses. The counter is
**global, deliberately not per-BOQ** — the opposite of `ra_no`. **A deleted
challan does not release its number.**

**Over-dispatch warns and never blocks**, which is the opposite call from the
RA over-claim guard and is deliberate. That guard is hard because it guards
money billed to a main contractor and an over-claim is a false claim. This is a
goods-movement note, and real sites have replacements, breakages, free issue
and returns; refusing a lawful movement here would only push it onto paper this
system never sees. An amber band names the lines and the movement stands.
Cumulative dispatched quantity is derived across the revision chain and never
stored.

**The rows are snapshotted at save** and matched to the BOQ on `line_id`
(§1.4), including the parent specification clause for any ticked size — so
unlike `/ra/print`, this document reads nothing at all from the live BOQ
(§1.2).

⚠ **The ~20 blank ruled rows on their form are deliberately not reproduced.**
They exist because DC54 is a spreadsheet printed for a human to write more
lines on by hand. A generated challan lists exactly what left the yard, and
blank ruled rows under a signature are an invitation to add a line after the
receiver has signed for it. Raising a second challan is cheap and leaves a
trail. **Worth confirming with them** — they may want the blank rows back for
hand-written additions at the gate.

⚠ **Whether their challan particulars satisfy Rule 55 of the CGST Rules is a
question for their CA and is not answered here.** Their DC carries no HSN, no
taxable value and no tax rate, and the system reproduces that faithfully. See
[ABOUT.md §7](ABOUT.md) gap 20 and §3 of this file.

→ [ABOUT.md §5](ABOUT.md) (`/dc`) for the pages, §2e for the shared line
picker; [tests/test_challan.py](tests/test_challan.py).

---

### 6 · Raise RA1 from the BOQ — ✅ Delivered, no charge

`/boq/view` now carries **`+ RA · Supply`** and **`+ RA · Installation`** in
its action bar, beside *Revise*.

**Built ahead of the Phase 2 gate, and correctly so** — §0's exemption. RA
billing against a BOQ was sold under MG/SF/2026-01 and the billing itself
worked; there was simply no way to reach it from the schedule on screen. That
is a reachability defect in delivered scope, the same class as the BOQ revision
chain being complete but uncalled, and it is not chargeable as new work.

**It was a smaller job than it read as, and the reason is worth keeping.**
When this was scoped, the assumption was that raising a bill from a BOQ meant
building a prefill. It did not. `/ra/create?boq=<id>&leg=<leg>` had always
built the complete claim grid from the schedule — approved quantity,
claimed-to-date, balance and rate per line — and **there is no blank RA entry
form in this app**: with no `boq` parameter the route renders its BOQ picker
instead. The only thing missing was a way in from the schedule on screen; the
operator had to leave the BOQ they were looking at and find it again in `/ra`.

**Approach.** A link, and nothing else. Built with `url_for` in the same
one-way style as the existing RA chips — `boq.py` still may not import `ra.py`
(§1.1) — and `/ra/create`, `_entry_form` and `_claim_rows` were not touched.
Two buttons because a bill covers one leg by construction.

**Offered only on the tip of a revision chain.** A claim is measured against
what is approved now, so a superseded BOQ shows no control; the *Revise* button
is suppressed by the same single predicate, and it names what replaced it, so
the page says why. One caveat is recorded in ABOUT.md §7 gap 16b: the BOQ page
and the RA picker answer "is this the tip?" with two different functions that
diverge on a hand-edited fork.

→ [ABOUT.md §5](ABOUT.md) (`/boq`) — *"RA billing starts here"*;
[tests/test_boq_ra_entry.py](tests/test_boq_ra_entry.py).

---

### 7 · Tax Invoice directly from the BOQ — ↩ Answered differently

**Not being built as its own path.** The need is met by a **full-value RA
prefill**: an RA bill claiming the full approved quantity is the tax invoice,
and `/ra/print/<id>` already renders it as one. Building a second route to the
same document would create two records that can disagree about one supply.

**Proforma Invoice from the BOQ is a separate matter — it is Pending and is
being built.** Like items 4 and 5 it is a BOQ-chain document: `boq.py` may not
import `proforma.py` (§1.1), so it does not go through the existing
`/proforma` module.

✅ **The dead premise is closed.** `ra.py` and its tests used to assert that an
RA bill is not a tax invoice, while the client's real as-submitted bill is
headed *Tax Invoice*. The assertion was **inverted, not deleted**
(`test_ra_carries_tax_invoice_record_shape` and
`test_ra_forbids_improper_tax_coupling`), and the last two comments still
carrying the old premise — `ra.py:66-68` and the section banner in
`tests/test_ra_record.py` — were corrected on 15 August 2026 alongside item 3.

⚠ **Still not unlocked by any of that:** `quotation._tax_lines()` remains
prohibited to `ra.py` on its own three reasons, which survive the inversion
untouched — [DOMAIN.md §4.9](DOMAIN.md),
[INTRODUCTION.md §7](INTRODUCTION.md).

→ [ABOUT.md §5](ABOUT.md) (`/ra`); [DOMAIN.md](DOMAIN.md) for the
tax-invoice requirement.

---

### 8 · Record payment received against an RA bill — ✅ Delivered

Amount received, balance, and that balance carried onto the next RA bill.

⚠ **Built on 14 August 2026 under the §0 override, with MG/SF/2026-02 still
unsigned.** This is **new scope and remains chargeable** under that quotation —
it is not a §0 exemption, and starting it early changed when it was built, not
what it costs. See §0's override block.

**Built as specified.** Receipts have **their own collection**, `receipts`,
keyed to the bill they pay (§1.3) — not embedded on the RA bill and not on the
BOQ, where they would eat the headroom under `boq.MAX_JSON_BYTES`.

**The previous-balance figure is SNAPSHOTTED** onto each bill by
`ra.create_ra()` at the moment it is raised, and every renderer reads it off
that record. It is not recomputed at print, and not recomputed on edit either.
`tests/test_receipts.py` proves it the strong way: it renders a bill, then adds
a receipt, corrects another and deletes a third underneath it, and asserts the
printed page is **byte-identical**.

**Where the frozen figure and the live ledger disagree, both are shown.**
Editing or deleting a receipt after a later bill has snapshotted its effect is
**allowed** and never touches that bill; the edit form and the delete
confirmation name the bills that will not move, and `/ra/view` flags the
divergence on each of them afterwards. Refusing the correction would protect a
document that is already immune while leaving the ledger permanently wrong.
DOMAIN.md §6: surface it, name it, never silently correct it.

**Receipts follow the revision CHAIN, not the BOQ record** — a payment against
a bill raised on revision 0 still counts once revision 1 is live. Summing
against one record would reset the carried balance to zero on every revision,
which is the trap `claimed_by_line()` already exists to avoid.

⚠ **ASSUMPTION, STILL NOT CONFIRMED BY THE CLIENT — and now built on.** Unpaid
amounts are **not** re-billed as line items on the next RA; the carried balance
is a memo on the face of the bill, absent from `claim_subtotal`, from every tax
figure, from `net_payable`, from `grand_total` and from the over-claim guard.

This was previously marked *"do not build on this assumption until they confirm
it"*. It was built on anyway, on the same 14 August decision as the override
above, and the assumption is recorded in three places rather than buried: in
the record shape comment at `ra.create_ra()`, in
[ABOUT.md §3](ABOUT.md) (RA Bill), and in §3 below, which stays open.

**What changes if they say no.** An arrear re-billed as a claim row would be
taxed a second time on a value already taxed once, and would inflate the
cumulative claim against the approved schedule until the over-claim block
refused a bill for the wrong reason. The test that pins the current behaviour
(`test_the_carried_balance_is_not_billed_taxed_or_claimed`) names itself as
pinning an assumption, so it is the first thing a future reader will find.

**Also shipped, not in the original ask:** `ra.can_delete()` refuses to delete
a bill that has receipts against it — deleting one would leave the money filed
against a document that no longer exists. `/receipt/delete` is POST-only behind
a GET confirmation, with its own test that a GET destroys nothing (§7.9f).

→ [ABOUT.md §2c](ABOUT.md) for the import direction and why the arithmetic
lives in `ra.py`; [ABOUT.md §3](ABOUT.md) (Receipt) for the record shape;
[ABOUT.md §5](ABOUT.md) (`/receipt`) for the pages;
[tests/test_receipts.py](tests/test_receipts.py).

---

### 9 · Employee / miscellaneous charges section — ✅ Delivered

**Delivered.** A separate ledger for recording business expenses (travel, food, wages, etc.) that do not appear in any BOQ.
- Standalone collection `STORE["charges"]`.
- The ledger does not compute margin or net profit (per item 10's deferred status).
- `taxable_amount` and `gst_rate` are stored; `gross_amount` is derived dynamically for display.
- Editable charge heads list via `/settings`.
- Optional association with a project.

---

### 10 · Project folder grouping BOQs, feeding a net profit/loss view — 🚧 Structure Built (Pass A)

**Pass A (Structure Only)** has been implemented. Projects are now a top-level entity, and they act as folders that group BOQs (and their entire revision chains), Proforma Invoices, and Purchase Orders. The `projectview.py` module provides the UI for viewing project details and managing attached documents. By design, no financial figures or profit/loss calculations are shown at this stage.

**Pass B (Profit / Loss View)** remains **Deferred — not scoped**. The commercial logic to compute true profitability requires strict definitions of cost and revenue, which are yet to be finalized.

**Not scoped.** Raised in the meeting, not specified.

Worth knowing before it is scoped: job costing in this app is **material
only** — no labour, no overhead, no allocation of a stock purchase across the
jobs that consume it. A "net profit/loss" view built on what exists today
would be a gross material margin with a name that overstates it, which is a
worse outcome than not having the page.

→ [ABOUT.md §7](ABOUT.md) gap B5.

---

## 3. Open questions with the client

Answers to these are blocking. None of them may be guessed at, defaulted, or
inferred from the seeded data.

1. **The GST head / place-of-supply determination.** Which head applies —
   CGST+SGST or IGST — and the place of supply with its State code, which is a
   Rule 46 field and is absent from the printed RA bill entirely. **Pending
   their CA. It must not be guessed at**, and no default may be changed in the
   meantime. Technical detail: [ABOUT.md §7](ABOUT.md) gap 15.

2. **Whether e-invoicing applies to their turnover band.** IRN plus a signed
   QR code is mandatory under Rule 48(4) above a turnover threshold, and the
   same threshold decides how many HSN digits must print. A document out of
   this app is a valid manual tax invoice below the threshold and **not** valid
   above it. We cannot answer this from anything we hold.
   → [ABOUT.md §7](ABOUT.md) gap 9b.

2b. ⚠ **Whether their delivery challan satisfies Rule 55 of the CGST Rules, and
   whether an e-way bill obligation attaches.** Their DC54 carries no HSN, no
   taxable value and no tax rate or amount, and item 5 reproduces that
   faithfully — **we built their document, not a compliant one, and those are
   not necessarily the same thing.** The movement on the sample is Navi Mumbai
   to Bangalore, which is interstate. **Pending their CA.** No agent may encode
   a guess about tax law in this repo: this sits beside question 1 and is
   answered the same way, by them. Technical detail: [ABOUT.md §7](ABOUT.md)
   gap 20.

3. **Retention % and mobilisation-advance figures.** The `deductions` shape
   exists and is deliberately empty; both fit it. We need their actual terms,
   per project if they differ, before anything is computed rather than typed.

3b. ⚠ **Whether an unpaid amount is re-billed on the next RA, or merely
   stated.** Item 8 assumes **merely stated** — a memo line carrying no GST and
   no claim row. **This question is no longer merely open: it has been built
   on**, on the 14 August decision recorded in §0. Answering it "re-bill them"
   is a real change, not a display tweak — see item 8 for what it moves. Ask
   them before the next RA bill goes out.

4. **Five complete BOQs and five as-submitted RA bills, still outstanding
   from them.** Everything above is being designed against one real schedule
   and one real bill. The item-numbering collapse that `line_id` exists to fix
   (§1.4) was found *because* a real workbook arrived; the remaining ten
   documents are the only way to find the next one before the client does.

---

*Section 2's change list is the client meeting of **10 August 2026**, and that
is what it still records. **This file as a whole is later than that**: §0 has
since taken dated blocks on **14, 15 and 16 August 2026** (three overrides and
one authorisation) and a **SUPERSEDED IN PART** block on **23 August 2026** — so
a reader who takes the 10 August date as the file's currency will miss every
commercial decision taken since, which is most of them. **Last updated 23 August
2026.** Phase 3 is a different meeting and a different file:
[CLIENT_CHANGES-2.md](CLIENT_CHANGES-2.md), 19 August 2026.*

*When an item's status changes, change it here and in [STATE.md](STATE.md) —
this file records the status, STATE.md orders the work. **When a dated block is
added to §0, update the date above in the same edit.***
