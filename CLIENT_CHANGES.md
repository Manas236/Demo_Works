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

> ### ⚠ OVERRIDE — 29 August 2026, by Manas Gawde — FOURTH block of this date: B6 and B7, the approval ladder
>
> **A new block, not an amendment, and the fourth one dated 29 August 2026.**
> The three blocks above it — `86902ef` (extra PO lines and C4), the narrow
> `quotation.py` unfreeze with the Operation Head ruling, and the third (C5, the
> navigation re-baseline, the alias cutback) — **have not been edited,
> reformatted, re-scoped or extended by a single character.** Each says what it
> said when it was written and each covers what it named. This is the **twelfth
> occasion overall and the seventh that reaches into Phase 3**.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated a fourth time, not softened
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending", it is not "with the client", and it is not awaiting a countersign.
> **It is expired.** This is the **fourth** override taken against a lapsed
> quotation, and a fourth is not evidence that the first three made it routine.
> **A lapsed quotation is a stronger reason to record and a weaker reason to
> build.** Nothing below is evidence that the gate has been met or lifted.
>
> #### What proceeds — two items, and only these two
>
> - **B6 — the approval ladder, AUTHORISED.** CC-2's B6 is a three-step
>   sequential ladder on charges (Director → Operation Head → HR), a two-approver
>   requirement on RA / Tax Invoice / PO (Operation Head + Director), **any one
>   Director's approval sufficient**, and the load-bearing rule that **a user
>   cannot approve a record they created** — checked against the record's
>   creator, not against the approver's role. Without that rule union permissions
>   defeat the ladder, which is CC-2's own stated reason for it.
>
> - **B7 — unapproved documents are view-only, AUTHORISED.** CC-2's B7 is that
>   an unapproved document **may be viewed but not printed or downloaded**, with
>   the print and download routes gated on approval status and a print stylesheet
>   so `Ctrl+P` does not walk around the gate.
>
> #### ⚠ The `created_by` backfill MUTATES LIVE RECORDS, and that is authorised
>
> Every approvable record gains a `created_by`, and records written before the
> field existed have no creator to record. **This is the first pass since the
> access-control layer that rewrites existing rows rather than only adding
> behaviour**, and it is authorised on that understanding: a backup is taken
> first, and the backup taken before this pass is the last one that will match
> the pre-migration shape.
>
> **Grandfathered records are approvable, and the exception is pinned so it
> cannot grow.** Refusing approval on every pre-existing record would strand
> live bills; allowing it silently would pretend the creator-cannot-approve rule
> held when it did not. Neither is acceptable, so the record carries an explicit
> marker that it predates the approval system, **on screen only and never on
> paper**, the count is recorded at migration time, and a test fails if any
> record created after the migration lacks a creator. **The test is the point of
> the rule** — without it the exception becomes a permanent hole.
>
> #### Still gated, untouched, and not started
>
> **B8, C1 and C2**, and the two BLOCKED items **C3** and **C6**. Not one of them
> is started and no groundwork is laid for any of them.
>
> ⚠ **C2 becomes buildable when this lands, and that is NOT an authorisation to
> build it.** The third block of this date recorded that C2 waits on B6 because
> its approved quantity feeds RA-Installation and an unapproved measurement is
> a number somebody typed. B6 landing removes that engineering obstacle and
> **removes nothing else**: C2 is priced in MG/SF/2026-02, MG/SF/2026-02 is
> expired, and C2 still needs an override block of its own that names it. **That
> a thing has become possible is the most common way this gate gets walked
> through by accident**, and it is recorded here precisely so the next pass does
> not mistake the one for the other.
>
> #### Chargeability
>
> **B6 and B7 are priced in MG/SF/2026-02 and stay priced there.** This is not a
> §0 no-charge exemption: that exemption covers defect and reachability fixes
> against scope already sold under MG/SF/2026-01, and an approval ladder is new
> capability. Building it early changed **when** it was built, not **what it
> costs** or **who agreed to it** — and the quotation that prices it has lapsed.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. That B6 and B7 were authorised does
> not authorise B8, C1 or C2, and it emphatically does not open C6.
> **An override is a decision the client-facing owner takes and records; it is
> never one an agent may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, items 8, 3, 2, 4 and 5, the whole of the Phase
> 3B access-control layer, the three Phase 3A items of 27 August, the three of
> 28 August, C4, C5 **and now the B6/B7 approval ladder** were built against a
> quotation that has **lapsed** — and the extra-lines work, together with the
> cutback that repairs it, was built against **no quotation at all**.

> ### ⚠ OVERRIDE — 29 August 2026, by Manas Gawde — FIFTH block of this date: C2 and C1, the measurement document and the order of working
>
> **A new block, not an amendment, and the fifth one dated 29 August 2026.**
> The four blocks above it — `86902ef` (extra PO lines and C4), the narrow
> `quotation.py` unfreeze with the Operation Head ruling, the third (C5, the
> navigation re-baseline, the alias cutback) and the fourth (B6 and B7) —
> **have not been edited, reformatted, re-scoped or extended by a single
> character.** Each says what it said when it was written and each covers what
> it named. This is the **thirteenth occasion overall and the eighth that
> reaches into Phase 3**.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated a fifth time, not softened
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending", it is not "with the client", and it is not awaiting a countersign.
> **It is expired.** This is the **fifth** override taken against a lapsed
> quotation, and a fifth is not evidence that the first four made it routine.
> **A lapsed quotation is a stronger reason to record and a weaker reason to
> build.** Nothing below is evidence that the gate has been met or lifted.
>
> #### What proceeds — two items, and only these two
>
> - **C2 — the measurement document, AUTHORISED.** CC-2's C2 is three lines:
>   *"Raised from the BOQ. Approved measurements become the source of
>   installation quantity on RA-Installation."* That is the whole of it, and
>   the shortness is recorded here rather than papered over — see the
>   unspecced-subsystem note below.
>
> - **C1 — the order of working, AUTHORISED.** CC-2's C1 states two chains,
>   `BoQ → Delivery Challan → RA-Supply` and `BoQ → Measurement →
>   RA-Installation`, and says *"Today installation quantity is typed straight
>   into the claim grid with nothing behind it. C2 closes that."* It states the
>   domain model; it does not state an enforcement mechanism, and the choice to
>   refuse **by URL** rather than by hiding a button is B5's established rule
>   applied here, not C1's text.
>
> #### ⚠ WHAT C2 DOES NOT SAY, recorded BEFORE it is built
>
> This is the pass-D lesson written down in advance rather than discovered
> afterwards. CC-2's C2 does **not** say any of the following, and every one of
> them is **ours, unspecced and unpriced**:
>
> - that a measured quantity may not exceed the BOQ quantity for its line;
> - that cumulative RA-Installation claims may not exceed the approved measured
>   quantity;
> - **which** approval ladder a measurement climbs — B6 names ladders for
>   charges and for RA / Tax Invoice / PO, and names measurement on neither;
> - that a measurement sheet prints at all, or what it looks like on paper.
>
> They are authorised as part of C2 because a measurement document without them
> is a form that records a number nobody checks. **They are not a delivered C2
> requirement and nobody may later cite them as one.** `PROGRESS.md` must say so
> plainly wherever C2 is marked BUILT.
>
> #### ⚠ PASS D BUILT `approval.can_modify()` ON CC-2's SILENCE, NOT ON CC-2's TEXT
>
> **Carried forward and recorded here because pass D disclosed it and no block
> yet holds it.** CC-2's **B7 governs printing and downloading only** — *"an
> unapproved document may be viewed, but not printed or downloaded"*, with the
> print and download routes gated and a print stylesheet so `Ctrl+P` does not
> walk round the gate. It says **nothing whatever about editing**.
>
> `approval.can_modify()` and every edit rule in it — an approved document is
> locked, a part-climbed ladder is locked, a rejected document returns to its
> creator only, an unstarted one is editable by its creator only — is a
> subsystem **we invented to fill that silence**. It is **ours, unspecced and
> unpriced**, it is not B7, and **`PROGRESS.md` must say so plainly wherever B7
> is marked BUILT**, so that nobody later cites it as a delivered CC-2
> requirement or as work MG/SF/2026-02 covers.
>
> Building it was the right call — an approval a later edit can walk underneath
> is not an approval — and that does not make it specified.
>
> #### ⚠ `_role_grants()` MUTATED LIVE ROLE RECORDS, and it is acknowledged retrospectively
>
> **Carried forward from pass D, which disclosed it.** The `created_by`
> migration was authorised to rewrite existing document rows and the fourth
> block of this date says so. What that block does **not** say is that the same
> migration also reached into `STORE["roles"]`: `_role_grants()` added the four
> `*.approve` permissions to four builtin role records that already existed in
> the live database, rather than only to `auth.BUILTIN_ROLES` in code.
>
> That is a second class of live mutation — identity data, not document data —
> and it was taken under a block that authorised the first. **It is
> acknowledged here rather than argued away.** It is recorded so that the next
> migration touching `users` or `roles` is authorised on its own terms and does
> not cite this one as precedent.
>
> #### ⚠ B7's PRINT GATE IS NARROWED BY TWO NAMED EXCEPTIONS, and by no others
>
> Pass D reported that B7, read strictly, took away two capabilities the client
> has today. Both are readmitted, and **only** these two:
>
> - **A DRAFT RA bill prints, carrying its DRAFT overprint.** B7 exists so an
>   unapproved **claim** cannot leave the building looking final. The overprint
>   is the opposite of that failure — it is itself the safeguard, and removing
>   the print removes the safeguard's purpose along with it. **The overprint
>   must still render**; a draft that prints clean is the thing B7 is actually
>   guarding against.
> - **A CANCELLED RA bill prints.** A cancelled bill is not a claim. It is the
>   audit record of a withdrawn one, and a record that cannot be produced is not
>   a record.
>
> **Every other unapproved state stays gated exactly as pass D built it** —
> pending, part-climbed and rejected all still refuse by URL. The narrowing is
> **draft-state and cancelled-state only** and it is not a general softening of
> B7.
>
> #### Still gated, untouched, and not started
>
> **B8**, and the two BLOCKED items **C3** and **C6**. Not one of them is
> started and no groundwork is laid for any of them. After this pass **B8 is
> the only buildable item left**; C3 stays blocked on BQ1 and BQ2, and C6 on
> CC-2's Open question 4.
>
> ⚠ **That C2 and C1 landing leaves B8 alone on the board is NOT an
> authorisation to build it.** B8 breaks the storage model — there is no
> `/static`, images are base64 data URIs, and `MAX_JSON_BYTES` is 300,000
> against a 2–5 MB photographed bill. It is priced in MG/SF/2026-02,
> MG/SF/2026-02 is expired, and it needs an override block of its own that
> names it. **That a thing has become the obvious next one is the most common
> way this gate gets walked through by accident.**
>
> #### Chargeability
>
> **C2 and C1 are priced in MG/SF/2026-02 and stay priced there.** This is not
> a §0 no-charge exemption: that exemption covers defect and reachability fixes
> against scope already sold under MG/SF/2026-01, and a measurement document is
> new capability. Building it early changed **when** it was built, not **what it
> costs** or **who agreed to it** — and the quotation that prices it has lapsed.
>
> The four unspecced additions listed above, the B7 narrowing, and
> `can_modify()` carried forward from pass D, are priced **nowhere at all**.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. That C2 and C1 were authorised does
> not authorise B8, and it emphatically does not open C3 or C6.
> **An override is a decision the client-facing owner takes and records; it is
> never one an agent may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, items 8, 3, 2, 4 and 5, the whole of the Phase
> 3B access-control layer, the three Phase 3A items of 27 August, the three of
> 28 August, C4, C5, the B6/B7 approval ladder **and now C2 and C1** were built
> against a quotation that has **lapsed** — and the extra-lines work, together
> with the cutback that repairs it, was built against **no quotation at all**.

> ### ⚠ OVERRIDE — 30 August 2026, by Manas Gawde — a cleanup pass: one live identity mutation, and no Phase 3 item
>
> **A new block, not an amendment, and the first one dated 30 August 2026.**
> The thirteen blocks above it — including all five dated 29 August 2026 —
> **have not been edited, reformatted, re-scoped or extended by a single
> character.** This is the **fourteenth occasion overall**. Eight of the
> thirteen above reach into Phase 3; **this one does not, and adds no ninth.**
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated a sixth time, not softened
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending", it is not "with the client", and it is not awaiting a countersign.
> **It is expired.** A sixth restatement is not evidence that the first five
> made it routine. **A lapsed quotation is a stronger reason to record and a
> weaker reason to build**, and nothing below builds anything.
>
> #### What proceeds — one thing, and only this
>
> **The role reconciliation of the cleanup pass, AUTHORISED.** It **mutates
> live role records** in `STORE["roles"]`, and this block is the authorisation
> the fifth block of 29 August 2026 said the next identity mutation would have
> to take on its own terms rather than by citing `_role_grants()` as precedent.
> It does not cite it. It is authorised here, on its own date, before it is run.
>
> **What it does, precisely:** `auth.ensure_builtin_roles()` deliberately never
> rewrites an existing role's permission list — once an Owner has edited what
> Director means, a restart must not undo it. The cost of that correctness is
> that **a permission minted in a later pass never reaches a database that
> already has its roles.** The reconciliation grants each builtin role exactly
> the permissions `auth.BUILTIN_ROLES` already gives it **in code**, and
> nothing else. **It invents no policy and decides nothing new**: every grant
> it makes was already decided, with its reasoning recorded, in the pass that
> minted the permission.
>
> #### ⚠ THE DRIFT IS WIDER THAN THE MEASUREMENT DOCUMENT — recorded, not buried
>
> The pass was commissioned to reconcile the six `measurement.*` permissions
> left unreachable by the fifth block of 29 August 2026. On measuring the live
> database it found **fourteen** permissions held by **no role at all**, not
> six. The other eight are **`employee.*` (C4)** and **`attendance.*` (C5)**,
> minted on 29 August 2026 and unreachable on this database ever since.
>
> **C4 and C5 have stood on the board as BUILT while nobody — including the
> Owner — could open either page.** That is the same defect as the measurement
> one, twice over and older, and it is recorded here because it means this
> mutation touches **more role records than the commissioning brief named**.
> All fourteen are reconciled, for the reason the pass was commissioned at all:
> the instruction was to fix the class and not the instance, and granting six
> of fourteen known orphans would be the instance.
>
> **No new capability is delivered by this.** Every one of the fourteen is a
> permission this application already ships, attached to a page already built
> and already marked built. The reconciliation makes reachable what was
> **already sold, already built and already paid for in effort** — it does not
> add a feature, a page, a route or a role.
>
> #### What is NOT authorised, and is not touched
>
> - **B8** — not started, no groundwork, and **attachment storage is not
>   begun.** The owner has proposed BLOBs; that is a separate authorised pass
>   and this is not it.
> - **C3** and **C6**, both BLOCKED — C3 on BQ1 and BQ2, C6 on CC-2's Open
>   question 4. Neither is opened, and nothing is wired into C6 or any P&L.
> - **No Phase 3 item is built, closed, or advanced by this pass.** The board
>   does not move: it stands where the fifth block of 29 August 2026 left it.
>
> #### Chargeability
>
> **Nothing here is chargeable, and it is not the §0 MG/SF/2026-01 exemption
> that makes it so.** That exemption covers defect and reachability fixes
> against scope sold under MG/SF/2026-01. These fourteen permissions belong to
> C2, C4 and C5 — **priced in MG/SF/2026-02, which has lapsed.** So the
> honest statement is narrower and worth making exactly: this pass **adds no
> capability and moves no price.** It repairs work already built, leaves that
> work priced where it was already priced, and bills nothing of its own.
>
> The reconciliation tool and the tests written to stop this class recurring
> are priced **nowhere at all**, like the other engineering the blocks above
> record as unspecced.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block authorises an
> identity mutation does not authorise the next one**, and a future migration
> reaching into `users` or `roles` needs a block of its own that names it —
> exactly as this block refused to cite `_role_grants()`.
> **An override is a decision the client-facing owner takes and records; it is
> never one an agent may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, everything the five blocks of 29 August 2026
> record as built — C4, C5, the B6/B7 approval ladder, C2 and C1 — was built
> against a quotation that has **lapsed**, and this pass has now made three of
> those items reachable by the people meant to use them.

> ### ⚠ OVERRIDE — 30 August 2026, by Manas Gawde — B8, file attachments, stored as BLOBs in their own table
>
> **A new block, not an amendment, and the SECOND one dated 30 August 2026.**
> The fourteen blocks above it — including the cleanup block of this same date
> — **have not been edited, reformatted, re-scoped or extended by a single
> character.** This is the **fifteenth occasion overall**, and the ninth that
> reaches into Phase 3.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated a seventh time
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending" and it is not "with the client". **It is expired.** A seventh
> restatement is not evidence that the first six made it routine.
>
> #### What is authorised
>
> **B8 — file attachments, AUTHORISED**, with attachments stored as **BLOBs in
> their own table**. The storage shape is the owner's own decision, taken on
> **30 August 2026**, and it is recorded here because it **departs from the
> letter of CC-2's B8**, which says "real file storage with a path held on the
> record". A filesystem path is what this application has no home for — there
> is no `/static` and no upload directory — so the owner chose a side table of
> BLOBs instead. **CC-2 is not edited to match**; the specification says what
> it says and this block is the decision that departs from it.
>
> The reasoning for a **side** table rather than bytes on the document record is
> architectural and is recorded so it is not undone by a later pass:
> `db.py` persists by **snapshot-and-diff**, re-serialising and re-hashing every
> record on every request. A multi-megabyte payload on a charge record would be
> re-hashed on every unrelated edit to that charge.
>
> #### ⚠ WHAT THIS BLOCK AUTHORISES, IT DOES NOT THEREBY DELIVER
>
> **B8 is authorised here and is NOT built.** The pass commissioned to build it
> **stopped before writing any attachment code**, on a gate its own brief set:
> establish first whether `db.py`'s snapshot-and-diff layer can carry a binary
> side table at all, and stop if it cannot rather than invent a second
> persistence mechanism beside it while the owner is away. **It cannot**, and
> the finding is recorded in the pass report and in ABOUT.md rather than worked
> around. **The board does not move. B8 stands AUTHORISED and UNBUILT**, and
> needs a decision from the owner on storage mechanism before it can proceed.
>
> An authorisation is not a delivery, and this block is deliberately worded so
> that a later reader cannot mistake the one for the other.
>
> #### What is NOT authorised, and is not touched
>
> - **C3** and **C6**, both **BLOCKED** — C3 on the owner's answers to BQ2 and
>   then BQ1, C6 on CC-2's Open question 4. Neither is opened, and no
>   groundwork is laid for either.
> - `attendance.py` stays unimported. `product.py` stays frozen.
>
> #### Chargeability
>
> **B8 is new scope priced into MG/SF/2026-02, which has lapsed**, and it
> remains chargeable there. Authorising it early changes **when** it is built,
> not **what it costs** or **who agreed to it**. Nothing was built under this
> block, so nothing is billable under it yet.
>
> The field-level escaping guard that this pass did deliver is priced
> **nowhere at all**, like the other engineering the blocks above record as
> unspecced. It is a defect fix against a guard that was asserting less than it
> appeared to, and it is recorded as **Delivered — no charge**.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block authorises B8 does
> not authorise C3, C6, or anything else**, and no override above is a
> precedent that clears the next.
> **An override is a decision the client-facing owner takes and records; it is
> never one an agent may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, everything built under the blocks above was
> built against a quotation that has **lapsed**.

> ### ⚠ OVERRIDE — 30 August 2026, by Manas Gawde — the wage unit is a DAY RATE, sites come from the address book, and two register screens
>
> **A new block, not an amendment, and the THIRD one dated 30 August 2026.**
> The fifteen blocks above it — including the cleanup block and the B8 block of
> this same date — **have not been edited, reformatted, re-scoped or extended by
> a single character.** This is the **sixteenth occasion overall**, and the tenth
> that reaches into Phase 3.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated an eighth time
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending" and it is not "with the client". **It is expired.** An eighth
> restatement is not evidence that the first seven made it routine.
>
> #### What this block records — the owner has corrected two facts about his own business
>
> These are not new requirements. They are **two things we got wrong about how
> Samruddhi actually operates**, told to us by the owner on 30 August 2026 after
> he opened the pages for the first time. Both change **delivered** items, and
> both **mutate live records**.
>
> **1. Wages are paid DAILY or WEEKLY, not monthly. AUTHORISED.**
>
> C4 stores `salary` as a **monthly** figure and C5 divides it by
> `wage_days_per_month`, a second setting invented during the C5 pass to fill a
> silence in CC-2. ⚠ **The silence was not there.** CC-2's C5 says *"Salary as 0
> or 1 based on attendance"* and *"OT = (salary ÷ 8) × hours"*, and its own note
> calls that formula **"1× ordinary rate"** — which is only true if `salary ÷ 8`
> is an **hourly** rate, i.e. if `salary` is a **day's** wage and 8 is hours in a
> day. Read as a monthly figure, "0 or 1 based on attendance" pays a whole
> month's salary for one day present. **CC-2's `salary` was always a day rate**,
> the monthly reading was ours, and the divisor solved a problem that never
> existed.
>
> So: the employee record carries a **day rate**, and `wage_days_per_month` is
> **deleted** — from `/settings`, from every calculation path, and from
> PROGRESS.md §4c, where a beyond-CC-2 item is **retired rather than added**.
> The OT multiplier stays a setting: that one is CC-2's own, and hardcoding it
> would still make this software compute a statutory underpayment.
>
> ⚠ **NO STORED FIGURE MAY BE CONVERTED ARITHMETICALLY.** A monthly figure
> silently reread as a day rate multiplies every wage by roughly twenty-six.
> Existing employee records are **marked** as carrying a figure entered under the
> old model, the page says on screen that the rate needs re-entering, and the
> wage calculation **refuses to produce a figure** for an unconfirmed employee
> rather than produce a wrong one. Attendance markings that snapshotted a salary
> are **history**: they are marked as computed under the old model and **their
> numbers are left exactly as they stand**.
>
> ⚠ **No pay-frequency field is added.** Weekly payment is a payout *cadence*,
> not a rate *unit* — attendance is daily, so a day rate serves both — and CC-2
> asks for no such field. If one turns out to be needed it is to be reported, not
> built.
>
> **2. Sites come from the ADDRESS BOOK, not from free text. AUTHORISED.**
>
> `site` on the employee master and on an attendance marking is free text
> somebody types, which is why the live data spells one place more than one way.
> It becomes a **picker over the address book**.
>
> ⚠ **Existing site strings must not be silently dropped or fuzzy-matched.**
> Where a stored string matches an address exactly it is linked; where it does
> not it is **left as it stands, marked unmapped, and reported in full** so a
> person can map it. A wrong automatic match moves labour cost to the wrong site,
> which is the failure this repository has already paid for once when
> `po_parts.py` shipped 156 invented aliases.
>
> **3. The two register screens the owner has actually seen. AUTHORISED, and
> no-charge.**
>
> `/attendance/` and `/dc/` are the **only two pages in this application that
> have ever been rendered to a human eye.** He reports that they are confusing,
> that the attendance table is misaligned, and that on Delivery Challans he
> cannot tell what to click. That is a reachability and usability defect against
> work already delivered, which is §0's standing exemption in its plainest form.
>
> ⚠ **No page the owner has not seen may be restyled**, and **no pinned print
> golden may move.** These are screen registers, not print sheets. If a change
> would reach a shared CSS constant a printed page also loads, the instruction is
> to **stop and report**, never to re-baseline a golden for a styling change.
>
> #### What is NOT authorised, and is not touched
>
> - **B8** — file attachments. **AUTHORISED on 30 August 2026 by the block above
>   and still UNBUILT.** It needs a **write-once, no-diff persistence path beside
>   `db.py`**, which is a decision with a schema change behind it and is the
>   owner's to take. ABOUT.md §4 carries the measurement that establishes
>   snapshot-and-diff cannot carry a BLOB. Nothing here starts it and no
>   groundwork is laid.
> - **C3** — the merged RA, **BLOCKED** on the owner's answers to BQ2 and then
>   BQ1.
> - **C6** — project profit and loss, **BLOCKED** on CC-2's Open question 4.
>   ⚠ Site-wise labour cost rolling up to a **project** is C6's, and an address
>   does **not** join to a project in this application. That shortfall is
>   **recorded in ABOUT.md and deliberately not solved here.**
> - `attendance.py` stays unimported by everything. `product.py` stays frozen.
>   `quotation.py` stays frozen except the narrow `view_quotation()` unfreeze.
>
> **The board does not move. It stays at 17 of 20.** C4 and C5 stay BUILT — this
> block **corrects** two delivered items rather than delivering a new one, and a
> correction is not a bar.
>
> #### Chargeability
>
> **The day rate and the site picker are corrections to C4 and C5, which are
> priced in MG/SF/2026-02 and stay priced there.** They are not §0 no-charge
> items: the §0 exemption covers defect and reachability fixes against scope sold
> under MG/SF/2026-**01**, and these two correct scope sold under
> MG/SF/2026-**02**. ⚠ **Nor are they a defect the client is owed for free
> merely because we read his specification wrongly** — that is a commercial
> question, it is the client-facing owner's, and **it has not been taken here.**
> What is recorded is that the work was done and against which quotation; who
> absorbs it is not an agent's call.
>
> **The two register screens are no-charge**, on §0's reachability exemption.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block corrects C4 and C5
> does not authorise B8, C3 or C6**, and no override above is a precedent that
> clears the next.
> **An override is a decision the client-facing owner takes and records; it is
> never one an agent may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, everything built under the blocks above — C4 and
> C5 among them, and now their correction too — was built against a quotation
> that has **lapsed**.

> ### ⚠ OVERRIDE — 30 August 2026, by Manas Gawde — FOURTH block of this date: the project→site link and the address-book guards
>
> **A new block, not an amendment, and the FOURTH one dated 30 August 2026.**
> The sixteen blocks above it — including the cleanup block, the B8 block and
> the day-rate / site-picker block of this same date — **have not been edited,
> reformatted, re-scoped or extended by a single character.** This is the
> **seventeenth occasion overall**, and the FIRST since 14 August 2026 that
> reaches into no Phase at all — it builds no CC-2 item and no MG/SF/2026-01
> item either.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated a ninth time
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending" and it is not "with the client". **It is expired.** A ninth
> restatement is not evidence that the first eight made it routine.
>
> **This work proceeds anyway, and Manas took that decision.** It is recorded
> here rather than assumed, on the terms every block above states: an override
> is a decision the client-facing owner takes and records; it is never one an
> agent may take, infer, or extend.
>
> #### ⚠ NEITHER ITEM BELOW IS IN CC-2. Both belong in PROGRESS.md §4c.
>
> **This is the load-bearing sentence of the block.** `CLIENT_CHANGES-2.md` was
> re-read against this work rather than trusted from memory, and it contains
> **no item covering a project→address join and no item covering address-book
> integrity guards**. C6 — *"project profit and loss"* — is the item that would
> eventually WANT the join, and **C6 is BLOCKED** on CC-2's Open question 4.
> Building the join is not building C6 and must never be presented as such.
>
> So both items go into **PROGRESS.md §4c**, the register of work built beyond
> CC-2's text, and **nobody may cite either as delivered CC-2 scope or as work
> MG/SF/2026-02 covers.** §4c's standing chargeability sentence applies to both
> without amendment: they are priced **nowhere at all**.
>
> #### What proceeds under this override
>
> **1. A project takes its site from the ADDRESS BOOK. AUTHORISED.**
>
> `projects.site_address` is free text somebody types, which is why this
> database holds *"Banglore, Karnataka"* on two projects and
> *"Bangalore, Karnataka"* on a third — one place, two spellings, on three of
> the four projects that exist. It gains `site_address_id`, an address-book
> link, and `site_address` is **demoted to the snapshot label** written from the
> chosen address at save. `/projects/create` and `/projects/edit` become a
> picker with no free-text fallback, beside an **"Add a new address"** link
> without which a user standing in front of an unfiled site has no move.
>
> ⚠ **The same rule as the employee and attendance backfill applies in full:
> nothing is fuzzy-matched.** An existing string matches an address label
> **exactly** or it creates one **verbatim, misspelling included**. Near misses
> and duplicate pairs are **printed and never applied**. A wrong automatic match
> puts a project on the wrong site and looks exactly like a right one.
>
> ⚠ **NO SPELLING IN LIVE DATA IS CORRECTED.** *"Banglore, Karnataka"* becomes
> an address record spelled *"Banglore, Karnataka"*. Resolving the pair against
> *"Bangalore, Karnataka"* is a **human** decision, taken by repointing one
> project and deleting the address that is then unreferenced.
>
> ⚠ **This does NOT unblock C6 and lays no groundwork claim.** It closes one
> of the two shortfalls C6 would have to close; the other — which of attendance
> wages and the BOQ installation base rate is authoritative — is Open question 4
> and is untouched. **The site→project ambiguity count** the backfill prints
> (the client has said one project = one site; he has **not** said one site =
> one project, and the live data already has two projects on one string) is
> **evidence recorded for a later pass and no guard is built on it.**
>
> **2. The address book gets integrity guards. AUTHORISED.**
>
> The book is now a master that four other modules point into — vendor on a
> draft PO and on a real PO, consignee on a challan, site on an employee, an
> attendance marking and now a project — and it has had **no delete guard at
> all**. Deleting a referenced address silently dangles every reference.
>
> - **Delete is refused** while anything references the address, and the
>   refusal **names the referencing records as chips**, `ra.party_lock_bills()`'s
>   shape. A refusal that does not say what is blocking it is a dead end.
> - **Archive** is added beside it, because a delete-refusal with no archive is
>   **a trap rather than a guard** — the finding the measurement delete guard
>   already made. An archived address leaves every picker, still resolves for
>   existing records, and can be un-archived. An address nothing references
>   stays hard-deletable; that is the cleanup path for duplicates.
> - **Editing a referenced address stays ALLOWED, and is logged** — user id,
>   timestamp, field, old value, new value, surfaced on the address page.
>   Freezing edits would make *"Banglore"* permanent with no repoint UI to fix
>   it. ⚠ The log records a **user id**, not a display name: `reprice_log`
>   records a display name and that is a known open gap, and this does not
>   repeat it.
> - **`type` is the one field locked** while references exist. Flipping a site
>   to a vendor drops it out of the site picker with nothing on screen saying
>   why.
>
> ⚠ **No merge-two-addresses operation is built**, and none is authorised. It is
> out of scope for this pass.
>
> #### Permissions — no new permission is minted
>
> Archive and un-archive sit under the **existing `address.delete`**, and the
> new address page under the existing `address.view`. Nothing is added to
> `auth.PERMISSIONS`, no role changes, and `tools/reconcile_role_permissions.py`
> therefore has nothing to reconcile. That is deliberate: three modules have
> already shipped unopenable on the live database because a pass minted a
> permission and never reconciled it, and the cheapest way not to repeat it is
> not to mint one. Archive is put with **delete** rather than with **edit**
> because it is what a refused delete becomes — the person who is stopped is the
> person who needs the alternative — and because pulling an address out of every
> picker is a wider act than correcting one field on it. Owner and Director hold
> `address.delete`; Sales Manager, Purchase Manager and Operation Head hold
> `address.edit` and do not.
>
> #### ⚠ THIS PASS MUTATES LIVE RECORDS
>
> `tools/backfill_project_sites.py` creates address records and writes
> `site_address_id` onto live projects. Dry-run by default, run dry first, and a
> `mysqldump` was taken before anything. `site_address` is **not** rewritten —
> it already holds the value the snapshot should hold.
>
> #### What is NOT authorised, and is not touched
>
> - **C6** — project profit and loss, still **BLOCKED** on Open question 4. No
>   figure is exported, `projectview.py`'s margin / total / net prohibition is
>   untouched, and `attendance.py` stays unimported by everything.
> - **C3** — the merged RA, **BLOCKED** on BQ2 and then BQ1.
> - **B8** — file attachments, **AUTHORISED on 30 August 2026 and still
>   UNBUILT**. Nothing here starts it.
> - The employee and attendance site pickers are **not changed**. `product.py`
>   and `quotation.py` stay frozen. No merge operation. No spelling corrected.
>
> **The board does not move. It stays at 17 of 20**, and the denominator stays
> 20. This block builds **no CC-2 item** — that is the whole reason both items
> land in §4c.
>
> #### Chargeability
>
> **Priced nowhere at all**, on §4c's standing sentence. It is not §0's
> MG/SF/2026-01 exemption, which covers defect and reachability fixes against
> scope already sold — the project→site link is new capability, not a repair to
> something sold. It is not MG/SF/2026-02 either, which prices C4, C5 and C6 but
> not the join that sits between them. ⚠ **Whether the address guards are a
> DEFECT the client is owed for free** — the book has shipped with no
> referential integrity since it was built — **is a commercial question, it is
> the client-facing owner's, and it has NOT been taken here.**
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block authorises the
> project→site link does not authorise C6**, and no override above is a
> precedent that clears the next.
> **An override is a decision the client-facing owner takes and records; it is
> never one an agent may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, everything built under the blocks above — and
> now this pass's work, which that quotation never covered at all — was built
> against a quotation that has **lapsed**.

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

> ### ⚠ OVERRIDE — 30 August 2026, by Manas Gawde — FIFTH block of this date: site labour on the project page, and a live data cleanup
>
> **A new block, not an amendment, and the FIFTH one dated 30 August 2026.**
> The seventeen blocks above it — including all four of this same date — **have
> not been edited, reformatted, re-scoped or extended by a single character.**
> This is the **eighteenth occasion overall**, and the SECOND consecutive one
> that reaches into no Phase at all.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated a tenth time
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending" and it is not "with the client". **It is expired.** A tenth
> restatement is not evidence that the first nine made it routine.
>
> **This work proceeds anyway, and Manas took that decision.** It is recorded
> here rather than assumed, on the terms every block above states: an override
> is a decision the client-facing owner takes and records; it is never one an
> agent may take, infer, or extend.
>
> #### ⚠ NEITHER ITEM BELOW IS IN CC-2. Both belong in PROGRESS.md §4c.
>
> **This is the load-bearing sentence of the block**, and it is the fourth block
> running to have to write it. `CLIENT_CHANGES-2.md` was re-read against this
> work rather than trusted from memory, and it contains **no item covering a
> labour section on the project page and no item covering a data-cleanup or
> demo-seeding tool.** C6 — *"project profit and loss"* — is the item that would
> eventually want a labour figure on that page, and **C6 is BLOCKED** on CC-2's
> **Open question 4**: whether attendance wages or the BOQ installation base
> rate is authoritative for labour cost. **Nothing below answers that question,
> and nothing below may be read as having answered it.**
>
> So both items go into **PROGRESS.md §4c**, the register of work built beyond
> CC-2's text, and **nobody may cite either as delivered CC-2 scope or as work
> MG/SF/2026-02 covers.** §4c's standing chargeability sentence applies to both
> without amendment: they are priced **nowhere at all**.
>
> #### What proceeds under this override
>
> **1. A SITE LABOUR section on `/projects/view/<id>`. AUTHORISED, and narrowly.**
>
> It lists **every attendance marking whose `site_address_id` equals this
> project's** — date, employee, status, OT hours, day rate, overtime and total,
> using `attendance.py`'s own cell rendering rather than a second copy of it.
>
> ⚠ **It is a PRESENTATION OF MARKINGS, and it is not a P&L authority.** It
> states what the muster already records, on the page of the project that shares
> the site. It performs no subtraction, states no margin, no project total and
> no net, and it is **not** an answer to Open question 4. A reader who takes the
> figure in it as "this project's labour cost" has taken a step this block does
> not authorise and the page itself refuses to make.
>
> ⚠ **THE MARKINGS ARE BOOKED AT A SITE, NOT TAGGED TO A PROJECT — and the
> section says so on its face.** This is the difference that makes the section
> honest or misleading, and there is nothing subtle about it. *"Expenses &
> Charges"* one panel up finds its rows by `charge.project_id`, an id somebody
> chose from a dropdown when they entered the charge. This section finds its
> rows by a join through a **third record, the address**, which nobody chose and
> which names no project at all. Where one address carries several live
> projects, **every one of those markings appears on every one of those project
> pages, showing the same money each time.** The section renders a visible note
> saying how many other projects share the site and naming them. It is not
> decoration and it may not be removed to tidy the page up.
>
> ⚠ **THIS BLOCK LIFTS TWO STANDING PROHIBITIONS, and names both rather than
> letting a test failure discover them.**
>
> - `ABOUT.md` §5 `/attendance` reads *"No figure on the dashboard, none on
>   `/projects/view/<id>`, none in `charge.py`, and no function any other module
>   calls."* **The clause about the project page is lifted by this block, and
>   only that clause.** The dashboard card stays counts-only and `charge.py`
>   stays forbidden in both directions.
> - `attendance.py` is imported by **nothing**, asserted at AST level by
>   `tests/test_attendance.py::test_nothing_imports_the_attendance_module`.
>   **`projectview.py` may now import it, and it is the only module that may.**
>   The guard is rewritten to assert exactly that rather than deleted, and the
>   old assertion is kept verbatim in a comment above it.
>
> **`projectview.py`'s own prohibition — lines 10–15 of its docstring — is NOT
> lifted and is not touched.** It reads *"Each panel shows the documents' OWN
> values and adds that one column up. What this page must never show is a figure
> that only exists by combining two panels — no revenue total, no cost total, no
> margin, no profit, no net, no balance."* A sum down the labour section's own
> single column is the **first** sentence, which five panels on that page
> already exercise through `_sum_cell()`; the prohibition is on the second.
> **No margin, project total or net is built under any reading.**
>
> **2. A LIVE DATA CLEANUP, `tools/clean_site_data.py`. AUTHORISED.**
>
> Dry-run by default, `--write` to apply, idempotent, printing a before/after
> inventory. It does three things and no fourth:
>
> - **Folds one duplicate address.** *"Banglore, Karnataka"* and *"Bangalore,
>   Karnataka"* are one place; the correctly-spelled record is canonical. Every
>   reference is repointed off the misspelled record via
>   `address.references_of()`, and the record — now unreferenced — is deleted.
>   ⚠ **This is a one-off repoint of ONE named pair. It is not a
>   merge-addresses engine and no reusable one is built.** The fourth block of
>   this date said the resolution of this pair is *"a HUMAN's to resolve"*;
>   this block is that human resolving it, in writing, before it is run.
> - **Repoints the unmapped `Banglore` site strings** onto the canonical
>   address, skipping any record the purge below removes.
> - **Purges five named test records** and what they cascade to.
>
> ⚠ **`Sify Bangalore`, `Sify 2` and `Sify3` are NOT purged**, nor are their
> clients or their BOQs. **`Sify3`'s `site_address_id` IS repointed** by the
> fold above, because it sits on the misspelled record and the misspelled record
> cannot be deleted while anything points at it. **A repoint onto the correct
> spelling of the same physical place is not a change to the project**: its
> name, client, BOQs, charges and documents are untouched, and the site it names
> is the site it always named. That distinction is authorised here explicitly so
> that no later reader has to guess whether the two instructions collided.
>
> ⚠ **`Hinjewadi Project Site` is a real address and stays.** No spelling is
> corrected in any record not named above.
>
> ⚠ **A PURGE THAT WOULD ORPHAN A DOCUMENT MUST STOP AND REPORT.** It may not
> force a delete and it may not decide on the human's behalf that a document is
> disposable.
>
> **3. A DEMO SCENARIO SEEDER, `tools/seed_demo_scenario.py`. AUTHORISED, with
> the standing rule it bends named in full.**
>
> ⚠ **`employees` and `attendance` are TRANSACTIONAL collections**, classified
> so by `tests/test_hardening.py` for reasons that are still exactly right: *a
> seeded employee is a person who does not exist carrying a salary they are not
> paid*, and *a seeded marking says somebody was on a site on a day and puts a
> wage against it.* **That rule is NOT relaxed.** What is authorised is a
> **command-line tool the operator runs deliberately**, which:
>
> - is **not called from any route, any render path, or any import** — nothing
>   in the application may seed it as a side effect, and a test asserts it;
> - marks every record it writes so `--purge` removes exactly what it created
>   and nothing else;
> - leaves `test_hardening.py`'s guarantee intact — a fresh install still has
>   an empty `employees` and an empty `attendance`, because the tool is not part
>   of the application.
>
> The marker exists for `--purge`, not to evade a test. **`test_hardening.py`
> inspects no record's fields**; it runs the app's seeders and looks for rows.
> Nothing an operator writes from a terminal is visible to it.
>
> #### What is NOT authorised, and is not touched
>
> - **C6 stays BLOCKED**, on Open question 4, exactly as it was. No margin, no
>   project total, no net, no P&L, and no answer to which labour figure is
>   authoritative.
> - **C3** stays BLOCKED on BQ1 and BQ2.
> - `employee.py ↔ charge.py` and `attendance.py ↔ charge.py` stay forbidden in
>   **both** directions.
> - **No Phase 3 item is built, closed, or advanced by this pass**, and the
>   board denominator stays **20**. The board does not move.
> - `product.py` and `quotation.py` are not opened.
> - The fifteen-module register table inconsistency recorded by
>   `tests/test_registers.py` is **not** taken on here. It is its own pass.
>
> #### Permissions
>
> **No permission is minted.** The section renders inside `/projects/view/<id>`,
> which is already classified `project.view`, and its labour detail is drawn
> only for a holder of `attendance.view` — a grant that already exists and
> already reaches Owner, Director and HR. A reader without it sees the section
> and a line saying the detail needs that permission, which is the honest answer
> and not a blank space. **Nothing is added to `auth.PERMISSIONS`, so
> `tools/reconcile_role_permissions.py` has nothing to reconcile** — and that is
> a measured claim, not an intention.
>
> #### Chargeability
>
> **Nothing here is chargeable.** It is not the §0 MG/SF/2026-01 exemption that
> makes it so: neither item is a defect or reachability fix against scope sold
> under MG/SF/2026-01, because neither item was ever sold. They are priced
> **nowhere at all**, like the other §4c engineering the blocks above record as
> unspecced. The cleanup and the seeder repair and populate a **development**
> database and deliver the client nothing.
>
> **One exception, and it is a real defect fix against work already delivered:**
> the attendance day table renders the unmapped-site marker as
> `BangloreSITE NOT MAPPED` — the chip's CSS class is defined only in
> `employee.py`'s stylesheet, which `/attendance/` never loads, so it prints as
> bare unstyled text welded onto the site string with no separator. That is a
> defect in C5 as shipped, on a page the owner has actually opened, and fixing
> it is covered by the standing exemption.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block authorises a live
> data mutation does not authorise the next one**, and a future tool reaching
> into live records needs a block of its own that names it. **An override is a
> decision the client-facing owner takes and records; it is never one an agent
> may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, C4, C5, C2, C1 and the B6/B7 ladder were all
> built against a quotation that has **lapsed**, and this pass has now put a
> reading of C5's data onto a second page.

> ### ⚠ OVERRIDE — 30 August 2026, by Manas Gawde — SIXTH block of this date: an attendance marking gains a PROJECT, and the two records left hanging are resolved
>
> **A new block, not an amendment, and the SIXTH one dated 30 August 2026.** The
> eighteen blocks above it — including all five of this same date — **have not
> been edited, reformatted, re-scoped or extended by a single character.** This
> is the **nineteenth occasion overall**, and the THIRD consecutive one that
> reaches into no Phase at all.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated an eleventh time
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending" and it is not "with the client". **It is expired.** An eleventh
> restatement is not evidence that the first ten made it routine.
>
> **This work proceeds anyway, and Manas took that decision.** It is recorded
> here rather than assumed, on the terms every block above states: an override
> is a decision the client-facing owner takes and records; it is never one an
> agent may take, infer, or extend.
>
> #### ⚠ NOTHING BELOW IS IN CC-2. It all belongs in PROGRESS.md §4c.
>
> **This is the load-bearing sentence of the block**, and it is the fifth block
> running to have to write it. `CLIENT_CHANGES-2.md` was **re-read in full
> against this work rather than trusted from memory**, and it contains **no item
> linking an attendance marking to a project.** C5's five bullets are
> presentee/absentee recorded daily, salary as 0 or 1 on attendance, *one
> employee = one site = one day*, `OT = (salary ÷ 8) × hours`, and a presentation
> table of *Employee — Site — OT time*. **Not one of them names a project.** The
> item that would eventually want the link is **C6** — *"project profit and
> loss"* — and **C6 is BLOCKED** on CC-2's **Open question 4**: whether
> attendance wages or the BOQ installation base rate is authoritative for labour
> cost. **Nothing below answers that question, and nothing below may be read as
> having answered it.**
>
> ⚠ **Attributing a marking is not the same act as costing a project**, and the
> distinction is the whole reason this is authorised while C6 is not. Open
> question 4 asks *which labour figure is authoritative*. This block asks *which
> project a day was worked for*. The second is a fact somebody on site knows and
> can record; the first is a commercial ruling nobody has taken. Recording the
> second does not take the first, and **a reader who treats the sum in the new
> panel as "this project's labour cost" has taken a step this block does not
> authorise and the page itself refuses to make.**
>
> So everything below goes into **PROGRESS.md §4c**, the register of work built
> beyond CC-2's text, and **nobody may cite any of it as delivered CC-2 scope or
> as work MG/SF/2026-02 covers.** §4c's standing chargeability sentence applies
> without amendment: it is priced **nowhere at all**.
>
> #### What proceeds under this override
>
> **1. A `project_id` ON AN ATTENDANCE MARKING. AUTHORISED, and narrowly.**
>
> The problem it exists for, stated plainly: `'Bangalore, Karnataka'` carries
> **four** live projects, and the fifth block of this date is what concentrated
> them there. **The site is not a strong enough key to attribute labour**, so a
> marking now says which project it is for.
>
> The shape is **`charge.py`'s and no second one is invented**: an **id somebody
> picked**, with the **name snapshotted beside it**. On `/attendance/mark` and on
> the marking edit form, a project picker **filtered to the projects carrying the
> chosen site's `site_address_id`**:
>
> - exactly **one** project on that site → **preselected**, so the common case
>   costs the operator no extra decision;
> - **more than one** → ⚠ **a choice is REQUIRED to save.** It is not defaulted,
>   not the first, not the most recent. Defaulting it is the whole defect wearing
>   a different hat: it would put a figure against a project nobody chose, which
>   is `po_parts.py`'s 156 invented aliases in a third register;
> - **zero** projects on that site → **blank is allowed and saves fine.** An
>   office or a store is a legitimate place to be marked and belongs to no
>   project.
>
> ⚠ **Changing the site clears a `project_id` that no longer belongs to it**, and
> **a marking may not carry a project whose site is not the marking's site.**
> That is asserted at the write and proved by mutation, not left to the form.
>
> ⚠ **AN ABSENT `project_id` MEANS LEGACY, NOT "NO PROJECT".** No third state
> marker is invented and **nothing is backfilled inside the application** —
> `project.is_legacy_site()` reading the **shape** rather than a mark is the
> precedent, one collection along. The bulk mapping is a tool an operator runs
> deliberately, below.
>
> **2. SITE LABOUR READS THE PROJECT — TWO GROUPS, VISIBLY SEPARATED.**
> **AUTHORISED.**
>
> `/projects/view/<id>`'s Site Labour section, built under the fifth block of
> this date, now shows **two labelled groups and never one silently merged
> list**:
>
> 1. **Booked to this project** — markings whose `project_id` is this project,
>    summed;
> 2. **At this site, unattributed** — markings on this project's site carrying no
>    `project_id`, **summed separately**, with the page saying in plain words
>    that they are attributed to no project and appear here because they were
>    booked at this site.
>
> ⚠ **The ambiguity note earns its place or it goes.** Where group 2 is non-empty
> **and** the site carries other projects, the note naming them **stays** — the
> money genuinely does appear on those pages too. Where group 2 is **empty** the
> note is **no longer true and is dropped**. Where the site carries other
> projects but every marking is attributed, the page **says nothing**: the
> ambiguity is resolved and a page that goes on warning about a resolved
> ambiguity teaches its reader to ignore the warning.
>
> ⚠ **`projectview.py`'s own prohibition — lines 21–26 of its docstring — is NOT
> lifted and is not touched.** *"Each panel shows the documents' OWN values and
> adds that one column up. What this page must never show is a figure that only
> exists by combining two panels — no revenue total, no cost total, no margin, no
> profit, no net, no balance."* **Two sums inside one panel is still one panel**,
> and neither is added to the other, to a charge, to a BOQ or to anything else on
> the page. **No margin, project total or net is built under any reading.**
>
> **3. `tools/backfill_marking_projects.py`. AUTHORISED.**
>
> Dry-run by default, `--write` to apply, idempotent, printing a before/after
> inventory. For each marking carrying a `site_address_id` and no `project_id`:
> if that site carries **exactly one** project, link it. If it carries **zero or
> more than one**, ⚠ **leave it and print it** — with the candidate project names
> in full, so a human resolves it by hand in the UI. **It never guesses, never
> takes the oldest and never takes the newest.**
>
> **4. THE TWO RECORDS LEFT HANGING BY THE FIFTH BLOCK ARE RESOLVED.**
>
> ⚠ **Project *"Banglore"* is NOT deleted, and this is the ruling the fifth block
> left to a human.** That block's tool **refused** the purge and said so;
> the refusal was correct and it stands. Hanging off it are
> `SF/BOQ/26-27/0007` and, under that schedule, **delivery challan 3**,
> **measurement sheet `SF/MS/26-27/0001` — the only measurement sheet in the
> database** — and **draft PO `SF/DPO/0003`**; the project also carries
> `SF/PO/26-27/0002` and **three charges**. **Losing the only measurement sheet
> costs more than keeping a test-looking project.** It is **renamed** to
> `ZZ TEST — Banglore (do not use)` so nobody demos it by accident, and **every
> attached document is left untouched.**
>
> ⚠ **The rename is authorised only while it breaks nothing.** If it would move a
> snapshot, a stored reference or anything on a printed document, it is **not to
> be done either** — report it and leave the record exactly as it stands. The
> expectation is that it breaks nothing, because every dependant snapshots
> `project_name` at its own write and none re-reads the live project; **that is
> to be verified rather than assumed.**
>
> **Project *"Test Supplier"* (client Manas)** — deleted **only if it has zero
> dependants**: no BOQ, delivery challan, measurement, purchase order, charge, RA
> bill or attendance marking. If it has **any**, it is renamed the same way and
> **not** deleted. What was found is enumerated either way.
>
> #### ⚠ THE SIFY3 REPOINT OF THE FIFTH BLOCK IS RATIFIED, NOT REVERTED — and this closes it
>
> The fifth block of this date authorised folding `'Banglore, Karnataka'` into
> `'Bangalore, Karnataka'` and repointing everything off the misspelling,
> **`Sify3` included**. That fold ran, the misspelled address is **gone**, and
> the pass that ran it recorded the collision between *"do not touch Sify3"* and
> *"delete the address Sify3 points at"* rather than resolving it silently.
>
> **It is ratified here.** ⚠ **Leaving `Sify3` pointing at a deleted record would
> be strictly worse than the contradiction that was resolved** — a dangling link
> reads on every page as a mapped record and is not one, which is exactly what
> `employee.resolve_site()` refuses to store. A repoint onto the correct spelling
> of **the same physical place** changes no fact about the project: its name,
> client, BOQs, charges and documents are untouched, and the site it names is the
> site it always named. **The call was made correctly and it is closed. Nobody is
> to revert it, and no later reader need re-open it.**
>
> #### What is NOT authorised, and is not touched
>
> - **C6 stays BLOCKED**, on Open question 4, exactly as it was. No margin, no
>   project total, no net, no P&L, and no answer to which labour figure is
>   authoritative. **A marking knowing its project is not a project knowing its
>   cost.**
> - **C3** stays BLOCKED on BQ1 and BQ2. **No RA bill is merged, split or
>   restructured.**
> - `employee.py ↔ charge.py` and `attendance.py ↔ charge.py` stay forbidden in
>   **both** directions.
> - **No Phase 3 item is built, closed, or advanced by this pass**, and the board
>   denominator stays **20**. The board does not move.
> - `product.py` and `quotation.py` are not opened.
> - **`Sify Bangalore`, `Sify 2` and `Sify3` are not touched**, nor are their
>   clients, their BOQs, or the address they now point at.
> - The fifteen-module table-helper refactor recorded by `tests/test_registers.py`
>   is **not** taken on here. It is still its own pass.
>
> #### Permissions
>
> **No permission is minted and no route is added.** The picker renders inside
> `/attendance/mark` and `/attendance/edit/<id>`, both already classified and
> both already write permissions; the two groups render inside
> `/projects/view/<id>`, already classified `project.view` with its labour detail
> already drawn only for a holder of `attendance.view`. The backfill is a
> command-line tool and owns no endpoint. **So `docs/ACCESS_MATRIX.md` must not
> move and `tools/reconcile_role_permissions.py` has nothing to reconcile —
> both to be MEASURED at the end of the pass, not intended at the start of it.**
>
> #### Chargeability
>
> **Nothing here is chargeable.** It is not the §0 MG/SF/2026-01 exemption that
> makes it so: none of it is a defect or reachability fix against scope sold
> under MG/SF/2026-01, because none of it was ever sold. It is priced **nowhere
> at all**, like the other §4c engineering the blocks above record as unspecced.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block authorises a second
> live data mutation does not authorise the next one**, and a future tool
> reaching into live records needs a block of its own that names it. **An
> override is a decision the client-facing owner takes and records; it is never
> one an agent may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, C4, C5, C2, C1 and the B6/B7 ladder were all
> built against a quotation that has **lapsed**, and this pass has now put a
> project key onto C5's records and a second reading of them onto the project
> page.

> ### ⚠ OVERRIDE — 2 September 2026, by Manas Gawde — B8's storage mechanism is DECIDED, and C3 is unblocked by answering BQ2 then BQ1
>
> **A new block, not an amendment, and the FIRST one dated 2 September 2026.**
> The nineteen blocks above it — including all six dated 30 August 2026, and
> **including the B8 block of that date whose storage choice this one replaces**
> — **have not been edited, reformatted, re-scoped or extended by a single
> character.** This is the **twentieth occasion overall**. ⚠ **A block that
> supersedes an earlier decision does so by standing beside it and saying so,
> never by editing it.** The second 30 August 2026 block still reads exactly as
> it did, BLOBs and all, and a reader who finds it first must be able to reach
> this one — so it is named here in full rather than quietly outranked.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated a twelfth time
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending" and it is not "with the client". **It is expired.** A twelfth
> restatement is not evidence that the first eleven made it routine, and this
> block authorises the **last unbuilt item of 3B** and the **first of the two
> BLOCKED items of 3C** against a quotation that nobody has signed.
>
> **This work proceeds anyway, and Manas took that decision.** It is recorded
> here rather than assumed, on the terms every block above states: an override
> is a decision the client-facing owner takes and records; it is never one an
> agent may take, infer, or extend.
>
> ---
>
> #### 1. B8 — the storage mechanism, DECIDED: real files on disk, path on the record
>
> **B8 was authorised on 30 August 2026 and has stood AUTHORISED and UNBUILT
> since**, because the storage shape that block chose — **BLOBs in their own
> table** — was put to the test its own brief demanded and **failed it**. That
> finding is not disputed here; it is ratified. `db.py` persists by
> snapshot-and-diff, `_blob()` writes bytes through `json.dumps(default=str)`
> and reloads them as a **corrupted string with no exception raised**, every
> collection is one `data JSON NOT NULL` column, and `_sync_collection()`
> re-serialises every record of every collection on every request. ABOUT.md §4
> carries the measurements.
>
> ⚠ **The pass that stopped was RIGHT to stop**, and this block says so plainly
> because the alternative — inventing a second persistence mechanism beside
> `db.py` while the owner was away — is the failure mode the gate exists to
> prevent. Stopping on a gate is the system working.
>
> **THE DECISION: attachments are real files on disk, with a relative path held
> on a metadata record.** This is CC-2's own B8 text — *"real file storage with
> a path held on the record"* — so this block does not depart from the
> specification; **it returns to it**, and it is the 30 August storage choice
> that was the departure. CC-2 is not edited, in either direction: it said this
> all along.
>
> The terms of the decision, each of which is the owner's and is revisable:
>
> - **Files live outside any served directory.** There is no `/static` in this
>   application and none is created. The store sits beside `backups/` — a
>   gitignored runtime directory at the repository root, which is the
>   convention `tools/backup_db.py` already established for data that is
>   confidential, large, and not part of the source tree.
> - **The path stored on the record is RELATIVE**, never absolute. An absolute
>   path publishes the disk layout of the machine the app runs on into a
>   database that gets dumped, and the dumps are handled.
> - **Only JPEG, PNG and PDF**, and the check is on the **file's actual leading
>   bytes**, not on its extension and not on the `Content-Type` the browser
>   claims. A renamed executable labelled `image/png` is refused.
> - **5 MB per file**, refused **before anything is written to disk**.
> - **Compulsory on a charge** — the 19 August list says *"Compulsory document
>   ATTACHMENT in the charge section"* and it is read literally.
> - **Optional on a receipt**, and this is not an inconsistency to be tidied
>   away later: CC-2 gives the reason in its own words — *"bank transfers often
>   have no separate slip, and compulsory would block honest entries."* ⚠ **A
>   later pass must not make it compulsory** without a block of its own.
> - **Deleting the parent deletes the file and the metadata row.** No orphans,
>   in either direction.
>
> ⚠ **CC-2's vocabulary warning is carried, not paraphrased.** *"Receipt"*
> already means the payment record in this application. What is attached to one
> is a **proof of payment** — a bank slip, a cheque image, a UTR advice — and
> the word "receipt" is not to be overloaded to mean the attachment.
>
> #### 2. C3 — UNBLOCKED, by answering BQ2 and then BQ1, in that order
>
> **C3 has been BLOCKED since 30 August 2026** on the owner's answers to **BQ2**
> and then **BQ1** — CC-2's own open build questions, explicitly *"not to be put
> to the client"* and explicitly to be settled **before** C3 is built, never
> inside a build step. They are settled here, in a block of their own, ahead of
> any code.
>
> ⚠ **BOTH ANSWERS ARE THE OWNER'S AND NEITHER IS THE CLIENT'S.** They are
> recorded in this style precisely so that a chartered accountant who disagrees
> can find them, name them, and have them changed. Neither is a finding; both
> are rulings.
>
> ##### BQ2 — answered FIRST, because BQ1 is not stable without it
>
> The repo says both. `PHASE4_RA_DESIGN.md` §2 says `ref` inherits Rule 46(b)'s
> 16-character cap **if** the RA bill is a tax invoice; §5 of the same file says
> it does not; the `[AMENDED 8 Aug 2026]` note satisfies §2's antecedent while
> §5's conclusion still denies the consequent; and the code sides with §5 at
> `_REF_CAP = 64`.
>
> **THE RULING, and it splits the question rather than picking a side:**
>
> - **An RA bill's `ref` is OUR document number and keeps its 64-character
>   budget.** `_REF_CAP` is **not** changed and no existing reference moves. §5
>   is right about `ref`.
> - **The statutory serial is `tax_invoice_ref`, it is a different field, and
>   it IS subject to Rule 46(b)'s 16-character cap.** §2 is right about the tax
>   invoice number. The two documents were never arguing about the same field.
>
> ⚠ **This makes `ra.py`'s comment above `_REF_CAP` a DEAD PREMISE and it is to
> be corrected in the same pass**, not left standing: *"No 16-character cap.
> That is Rule 46(b)'s limit on a TAX INVOICE number, and **this document is not
> one**"*. The conclusion survives — `ref` genuinely has no cap — but the reason
> given for it is the ruling the 8 August amendment reversed. A right answer
> resting on a dead reason is how the next reader gets it wrong.
>
> ##### BQ1 — answered SECOND: an independent series, and the collision dissolves
>
> BQ1 asks which of **three** serials is the statutory invoice when a merged
> document mints one over two source bills that *"each already carry one"*.
>
> **THE RULING: the two source bills never spent a statutory serial, so there is
> no third.** BQ2's answer is what dissolves it. A leg's `ref` is our document
> number; the statutory number is `tax_invoice_ref`; and the merged document
> mints **its own**, from **its own dedicated counter**, **derived from neither
> leg's reference**.
>
> Derivation was refused for a measured reason rather than a stylistic one:
> `SF/RA/26-27/0004` is **exactly 16 characters**, so there is **no room inside
> Rule 46(b)'s budget to decorate a leg's number into a unique merged variant**.
> A scheme that must truncate to fit is a scheme that will collide.
>
> ⚠ **The new series must NOT collide with `invoice.py`'s.** `invoice.py`
> already mints `SF/TI/26-27/0001` at `cap=16` for the sell-side tax invoice.
> Two counters both emitting a `TI` number would put **the same statutory serial
> on two different documents**, which is the precise failure Rule 46(b) exists
> to prevent and would be strictly worse than the ambiguity being resolved. The
> merged document therefore takes a **distinct series string of its own**, and
> `ra.py`'s standing prohibition on importing `invoice.py` is **not** to be
> relaxed to share a counter.
>
> **Multiple invoice series are permitted** provided each is consecutive and
> unique within the financial year, which is what a separate counter under a
> distinct series delivers by construction.
>
> ⚠ **WHAT THIS RULING DOES NOT DO, stated so it is not read as more than it
> is:** it mints a series for the **merged** document **only**. A single-leg RA
> bill's `tax_invoice_ref` stays exactly what DOMAIN.md §4.2 already records — a
> **typed field with no counter behind it**, falling back to `ref` when left
> blank. **That gap is NOT closed here**, it is not in C3's scope, and a later
> pass that closes it needs a block of its own. §4.2's STATUS paragraph stands.
>
> ##### What is authorised, and on what terms
>
> **C3 — merged RA, AUTHORISED**, built to **CC-2's own invariants**, which are
> the specification and are not restated loosely here: the merged record holds
> **no claims of its own**; totals are the **sum of the two bills' stored
> totals** and are never recomputed from the live BOQ; a bill appears in **at
> most one live merged document**; a source bill inside a live merged document
> **cannot be cancelled**; **receipts stay attached to the source bills**; and
> the merge action is built **on the RA register from day one**.
>
> The merged document **follows the existing RA / TI / PO approval ladder** —
> Operation Head + Director, any one Director sufficient — because it is the
> document that raises the tax invoice and nothing in CC-2 or `approval.py`
> exempts it.
>
> #### What is NOT authorised, and is not touched
>
> - **C6** stays **BLOCKED** on CC-2's Open question 4. Nothing here answers it
>   and no groundwork is laid for it.
> - `quotation.py` and `product.py` stay frozen beyond their existing narrow
>   unfreeze.
> - **The single-leg `tax_invoice_ref` gap above is not closed.**
> - No attachment is made compulsory anywhere CC-2 does not say it is.
>
> #### Chargeability
>
> **B8 and C3 are both scope priced into MG/SF/2026-02, which has lapsed**, and
> both remain chargeable there. Authorising them changes **when** they are
> built, not **what they cost** or **who agreed to them**.
>
> Anything this pass builds that CC-2 does not name — and the approval-gating of
> an attachment behind its parent document's ladder is such a thing — is priced
> **nowhere at all** and goes to **PROGRESS.md §4c** under that section's
> standing sentence.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block authorises B8 and C3
> does not authorise C6, or anything else**, and no override above is a
> precedent that clears the next. **An override is a decision the client-facing
> owner takes and records; it is never one an agent may take, infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, everything built under the blocks above — now
> including the whole of 3B and five of 3C's six items — was built against a
> quotation that has **lapsed**.

> ### ⚠ OVERRIDE — 3 September 2026, by Manas Gawde — the single-leg `tax_invoice_ref` gap, the backup's missing half, and one guard made non-vacuous
>
> **A new block, not an amendment, and the FIRST one dated 3 September 2026.**
> The twenty blocks above it — including the 2 September 2026 block whose own
> closing words asked for this one — **have not been edited, reformatted,
> re-scoped or extended by a single character.** This is the **twenty-first
> occasion overall**.
>
> ⚠ **This block is the one the 2 September block named in advance.** That block
> wrote, of the single-leg `tax_invoice_ref`: *"That gap is NOT closed here, it
> is not in C3's scope, and a later pass that closes it needs a block of its
> own."* This is that block. It is a fresh dated authorisation, not a
> retrospective widening of the one that asked for it — amending an override to
> cover work it does not mention is precisely the act §0 forbids.
>
> #### ⚠ MG/SF/2026-02 REMAINS EXPIRED AND UNSIGNED — restated a thirteenth time
>
> The quotation lapsed on **28 August 2026** and that has not changed. It was
> sent on 21 August 2026, read by the client the same day, and **has never been
> answered** — no signature, no advance, no reply of any kind. It is not
> "pending" and it is not "with the client". **It is expired.** A thirteenth
> restatement is not evidence that the first twelve made it routine.
>
> **This work proceeds anyway, and Manas took that decision.** It is recorded
> here rather than assumed, on the terms every block above states: an override
> is a decision the client-facing owner takes and records; it is never one an
> agent may take, infer, or extend.
>
> ---
>
> #### 0. FIRST, AND IT AUTHORISES NOTHING: the reported RA over-claim was not one
>
> This pass was opened on an observation from the browser — that BOQ
> `SF/BOQ/26-27/0006` (*Work2*) showed a Total Basic Value of **₹9,585** while
> the two RA bills attributed to it, `SF/RA/26-27/0006` and `SF/RA/26-27/0007`,
> showed **₹885** and **₹10,425**, summing to **₹11,310** — **₹1,725 over**, with
> RA2 alone apparently exceeding the whole schedule.
>
> **It was investigated before anything was authorised, and there is no
> over-claim.** The two figures are not the same kind of figure:
>
> - **₹9,585 is tax-EXCLUSIVE** — the BOQ's basic value, and the tile that
>   carries it says *"taxes extra"* on its own face.
> - **₹885 and ₹10,425 are tax-INCLUSIVE** — each chip on the *"Running Account
>   bills raised"* strip renders that bill's `grand_total`.
> - The two bills' **`claim_subtotal`s** are **₹750 + ₹8,835 = ₹9,585**, which
>   reconciles against the schedule **exactly**.
> - **₹1,725 is the GST**: ₹135 + ₹1,590.30, less ₹0.30 of rounding.
>
> Each leg is claimed **once, at exactly its approved quantity** — one line,
> `line_id` `59e2b4b8afd2`, quantity 1 approved and 1 claimed on each of supply
> and installation. `ra.claimed_by_line()` and `ra.approved_by_line()` were run
> against the live records and agree to the unit; `ra.overclaims()` returns
> empty for both bills, and returns a breach for both the moment either claim is
> mutated to 2. **The guard did not fail to fire. There was nothing to fire on.**
>
> ⚠ **NO RA, BOQ OR CLAIM RECORD IS TOUCHED BY THIS PASS**, and none may be.
> The records are live financial data, they are not test fixture data — the
> strings *Work2*, `SF/RA/26-27/0006` and `SF/RA/26-27/0007` appear nowhere in
> `tests/`, `tools/` or `demo_data.py`, and the suite writes to an in-memory
> `STORE` under `DB_ENABLED=false` and never to MySQL at all.
>
> **What IS worth knowing** is that the `/boq/view` panel puts a tax-exclusive
> total beside tax-inclusive chips with nothing on the chips saying so. That is
> a presentation defect, it is **reported and NOT fixed here**, and it is not
> authorised by this block.
>
> ---
>
> #### 1. The single-leg `tax_invoice_ref` — AUTHORISED, and the gap closes forward only
>
> **DOMAIN.md §4.2 forbids deriving the tax invoice number from `ra_no`**, and
> `print_ra()` does exactly that whenever the field is left blank: it falls back
> `tax_invoice_ref` → `ref` → a string built from `ra_no`. The prohibition holds
> on every bill where the field is filled and fails silently on every bill where
> it is not.
>
> **THE DECISION: a single-leg RA bill mints its own statutory serial, from its
> own counter, on the same pattern C3 already established for the merged
> document** — and *the same pattern* is meant literally, not loosely. A second
> scheme invented beside the first is two things to keep in step.
>
> - **Its own series string**, distinct from every other series in the
>   application. It must not be `TI` (`invoice.py`'s sell-side serial) and it
>   must not be `MI` (the merged document's). One statutory serial on two
>   different documents is the precise failure Rule 46(b) exists to prevent.
> - **Capped at 16 characters** under Rule 46(b), through the same
>   `pipeline.fy_ref()` cap the other two use.
> - **FY-scoped and max+1 within the year, never len+1** — a gap must never
>   re-issue a number already quoted in somebody else's ledger.
> - **Minted at creation**, where C3 mints its own, and **never at print** — a
>   print route that writes is a print route that changes a document by being
>   looked at.
> - **A typed value still wins.** The field stays typeable; minting fills it
>   when the operator leaves it blank, which is the case §4.2 names.
> - ⚠ **`ra.py`'s prohibition on importing `invoice.py` is NOT relaxed** to
>   share a counter, and neither is any other import direction.
>
> ##### ⚠ Existing bills are a CLOSED HISTORICAL SET and NOT ONE IS REWRITTEN
>
> **No already-issued document's number is corrected by this pass**, and this is
> the term of the decision most easily lost. A tax invoice number that has been
> printed has been quoted in somebody else's books; silently replacing it is the
> act the max+1 rule exists to prevent, one register along.
>
> So the fallback in `print_ra()` **survives for records that predate this
> block, and for them alone**, exactly as `pre_measurement` and `created_by`
> preserve their own grandfathered sets. It is unreachable for every bill
> created afterwards, because every such bill carries a minted number.
>
> **The set is counted rather than estimated**, and the count belongs in the
> pass report, not here. **Whether any of it is backfilled is the owner's
> decision and is NOT taken in this block.** No agent may take it.
>
> ⚠ **`tests/test_merged_ra.py::test_a_single_leg_bills_tax_invoice_ref_is_UNCHANGED`
> pins the old behaviour and will fail.** It is to be **rewritten, never
> deleted and never weakened**, keeping its old assertion verbatim in a comment
> above the new one — it was right on the day it was written and it is the
> record of what changed.
>
> #### 2. The attachments directory joins the backup — AUTHORISED, no charge
>
> B8 shipped on 2 September 2026 with a hole its own documentation named:
> *"A `mysqldump` is no longer a complete backup of this application. The
> metadata rows are in the dump; the files are not."* A restore from a dump
> alone produces rows pointing at files that do not exist.
>
> `tools/backup_db.py` is extended to snapshot `attachment.root()` alongside the
> dump, under the **same stamp, the same label and the same directory** — the
> convention that file already established. **Proof is a restore**, not a green
> test: take a backup, delete a file, restore, and confirm the *file* comes
> back.
>
> **This is a defect fix against work delivered on 2 September 2026** and is
> **no charge**, on §0's standing exemption in its plainest form.
>
> #### 3. `claimed_by_line()` learns about merged documents — AUTHORISED, no charge
>
> CC-2 warns that copying claim rows onto a merged record *"would make the
> over-claim guard count the same quantity twice"*. The guard built for that
> warning does not currently look: `ra.claimed_by_line()` walks
> `STORE["ra_bills"]` and a merged document lives in `STORE["merged_ras"]`.
> `tests/test_merged_ra.py::test_merging_does_not_move_the_overclaim_guard`
> **says so in its own docstring** and records that the mutation was caught by a
> neighbouring shape test rather than by itself.
>
> A test that cannot fail for its own reason is not a guard. `claimed_by_line()`
> is extended to walk both collections, and the mutation must be caught **by
> that function**, proved by mutation rather than asserted.
>
> **This is a defect fix against work delivered on 2 September 2026** and is
> **no charge**.
>
> #### What is NOT authorised, and is not touched
>
> - **C6** stays **BLOCKED** on CC-2's Open question 4. Nothing here answers it.
> - `quotation.py` and `product.py` stay frozen beyond their existing narrow
>   unfreeze.
> - **No RA, BOQ, claim, receipt or merged record is created, edited or
>   deleted** on the live database.
> - **No already-printed `tax_invoice_ref` is rewritten**, and no backfill tool
>   for them is authorised.
> - The `/boq/view` tax-inclusive-versus-exclusive presentation defect is
>   **reported and not fixed**.
> - No attachment is made compulsory anywhere CC-2 does not say it is.
>
> #### Chargeability
>
> **Items 2 and 3 are defect fixes against scope already delivered and are no
> charge**, on §0's standing exemption.
>
> **Item 1 is priced NOWHERE.** It is not in MG/SF/2026-01, and MG/SF/2026-02
> tags it nowhere — DOMAIN.md §4.2 is a requirement this application has carried
> since Phase 2 and has satisfied *in part* ever since. It goes to
> **PROGRESS.md §4c** under that section's standing sentence. **No agent may
> invent a price for it or record it as delivered under either quotation.**
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block authorises these
> three items does not authorise C6, or anything else**, and no override above
> is a precedent that clears the next. **An override is a decision the
> client-facing owner takes and records; it is never one an agent may take,
> infer, or extend.**
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, everything built under the blocks above — now
> including the whole of 3B and five of 3C's six items — was built against a
> quotation that has **lapsed**.

> ### ⚠ OVERRIDE — 5 September 2026, by Manas Gawde — the dashboard's BOQ/RA visual cues, and a ruling that does NOT exist
>
> **A new block, not an amendment**, and the twenty-second occasion overall.
> **MG/SF/2026-02 is still unsigned and has in any case lapsed.** Manas
> instructed this work and instructed that it be recorded rather than the rule
> deleted, exactly as on every occasion above.
>
> #### What proceeded
>
> Four visual cues on the **existing** dashboard (`dashboard.py`, ABOUT.md §5,
> `/`): an open-BOQ count and an RAs-pending-approval count, a claimed-to-date
> total shown against open BOQ value, a recent BOQ/RA activity feed, and
> per-project claimed-against-approved bars. No new route, no new page, no new
> permission, no new nav entry; `docs/ACCESS_MATRIX.md` regenerates
> byte-identical.
>
> #### ⚠ THE BRIEF CITED A RULING THAT IS NOT IN THIS RECORD, AND IT IS NOT INVENTED HERE
>
> The instruction for this pass said to record the work as continuing an
> existing ***"Visual Dashboard is free, not chargeable"*** ruling of
> **19 August / 24 August 2026**. **No such ruling exists.** It was searched for
> in this file, in CLIENT_CHANGES-2.md, in ABOUT.md, in PROGRESS.md and in
> INTRODUCTION.md before this block was written, and what the record actually
> contains is close to its opposite:
>
> **CLIENT_CHANGES-2.md's *"Stated by the client, NOT in MG/SF/2026-02"* section
> carries "visual dashboard" as untagged lines 1 (Director) and 2 (Operation
> Head)**, and says of them, in terms:
>
> > *"Items 1 and 2 need a client ruling before they can be priced at all. A
> > dashboard already exists in this software (`dashboard.py`). Whether 'visual
> > dashboard' meant that dashboard, restricted by role, or a new analytics view
> > is **not answerable from any document we hold**, and the two differ by an
> > order of magnitude in cost. Ask him. **Do not take the cheaper reading
> > because it is cheaper**, and do not take the dearer one because it is
> > safer."*
>
> **So the question is open, and this pass does not answer it.** Recording this
> work as "free, not chargeable under an existing ruling" would have done three
> things the record forbids: asserted a client decision nobody has taken,
> silently adopted the cheaper of two readings that differ by an order of
> magnitude, and closed a question CC-2 exists to keep open. The nearest true
> statement is the one made here instead.
>
> #### Chargeability — unsettled, and left unsettled
>
> ⚠ **This work is priced NOWHERE.** It is not in MG/SF/2026-01 (the dashboard
> it extends predates that quotation, but these four cues did not exist), and
> MG/SF/2026-02 tags it nowhere — "visual dashboard" is untagged in CC-2 by that
> file's own finding. **No agent may invent a price for it, record it as
> delivered under either quotation, or record it as delivered no-charge.**
>
> **It is NOT a §0 no-charge exemption.** That exemption covers defect and
> reachability fixes against scope already sold under MG/SF/2026-01. Four new
> surfaces on a page are new capability, however modest, and calling them a
> defect fix would be the same silent inclusion this block refuses.
>
> ⚠ **One half of it genuinely is a defect fix, and only that half.** Every
> amount on the new band is tax-exclusive, which is the second of the two
> options ABOUT.md §7 **gap 31** sets out — the display bug that made
> `SF/BOQ/26-27/0006` read ~18% over-claimed on 3 September 2026 when it was
> claimed to exactly 100%. **`/boq/view` itself is untouched and gap 31 stays
> open there**, so this is a demonstration of the fix and not the fix; nothing
> here may be recorded as closing that gap.
>
> **Whether this is charged, absorbed, folded into a replacement quotation, or
> taken as part-answer to CC-2's untagged lines 1 and 2 is a commercial decision
> the client-facing owner has not yet taken.** It is recorded as unpriced so the
> decision stays visible when it is taken, rather than foreclosed by silence —
> the same treatment the extra purchase-order lines have carried since
> 29 August 2026.
>
> #### Not a Phase 3 item, and the denominator is still 20
>
> ⚠ **This is not one of CC-2's twenty items and must never be counted toward
> them.** It carries no 3A/3B/3C tag. The board stays at **19 of 20 BUILT ·
> 1 BLOCKED** — C6, still blocked on Open question 4, untouched by this pass.
> PROGRESS.md §4a carries this work outside the bars, beside the extra
> purchase-order lines, for the identical reason.
>
> *(⚠ The brief for this pass also stated the board "stays at 18/20". It was
> **19 of 20 BUILT** before this pass and is 19 of 20 after it. The figure is
> not moved by this work; the citation was simply stale, and is corrected here
> rather than propagated.)*
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block authorises four
> dashboard cues does not authorise C6, does not answer CC-2's untagged lines 1
> and 2, and does not authorise anything else.** An override is a decision the
> client-facing owner takes and records; it is never one an agent may take,
> infer, or extend — and neither is a *ruling*, which is what the citation this
> block declines to repeat would have been.
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, everything built under the blocks above was
> built against a quotation that has **lapsed**.

> ### ⚠ OVERRIDE — 6 September 2026, by Manas Gawde — the end-to-end chain driver, and the JOINT MEASUREMENT SHEET
>
> **A new block, not an amendment**, and the twenty-third occasion overall. The
> twenty-two blocks above it have not been edited, reformatted, re-scoped or
> extended by a single character. **MG/SF/2026-02 is still unsigned and has in
> any case lapsed** — it lapsed on 28 August 2026 and has never been answered.
> Manas instructed this work and instructed that it be recorded rather than the
> rule deleted, exactly as on every occasion above.
>
> #### What proceeds — two items, and only these two
>
> - **`tools/e2e_chain.py`, an end-to-end HTTP chain driver.** A standalone
>   script, in `tools/` beside `backup_db.py`, imported by no application
>   module and referenced by no committed application code. It drives a running
>   dev app over HTTP from an empty project to a fully claimed BOQ and asserts
>   the money tallies at every hop. **It is not a Phase 3 item, carries no
>   3A/3B/3C tag, and must never be counted toward CC-2's twenty.**
>
> - **The JOINT MEASUREMENT SHEET** — a redesign of the printed measurement
>   document (`measurement.py`) onto the client's own workbook layout: a
>   location × diameter matrix, countersigned by both parties.
>
> #### ⚠ THE BRIEF FOR THIS PASS CARRIED FOUR WRONG PREMISES, AND THEY ARE CORRECTED HERE RATHER THAN PROPAGATED
>
> Every one was found by reading the source, which is the only thing that has
> ever caught one. They are recorded because the first of them would have
> destroyed a shipped guard.
>
> **1. ⚠ "Measurement does not control the RA claim" — IT ALREADY DOES, and the
> instruction to decouple was WITHDRAWN.** The brief's §4.1 instructed that the
> installation claim must not be capped to the measured quantity, that the claim
> must not be prefilled from it, and that no per-line link from a measurement row
> to a BOQ `line_id` be added — describing the C1 gate as the only existing
> coupling. **All of that coupling already exists and ships today.**
> `ra.overclaims()` replaces the BOQ ceiling with `MS.approved_qty_by_line()`
> for the installation leg, and measurement rows are keyed by `line_id` through
> the shared picker. §4.1 was therefore not an instruction to leave things
> alone; **it was an instruction to delete two live guards**, and the new
> (location, dia) grid — which carries no `line_id` — would have deleted them as
> a side effect whether or not anybody intended it.
>
> Worse, it would have deleted them **silently and through a path that means
> something else**: `approved_qty_by_line()` returning `{}` is read by `ra.py` as
> *"this project predates measurement, keep the BOQ ceiling"*, the grandfather
> path `tests/test_measurement_pin.py` exists to pin. Every new sheet would have
> taken that path while showing as approved.
>
> And it contradicts **CC-2's C2**, which is two sentences long and one of them
> is *"Approved measurements become the source of installation quantity on
> RA-Installation."* That is the **only** thing about measurement CC-2 actually
> specifies; everything else in the module is ours.
>
> **The decision taken, by Manas on 6 September 2026, is that the cap STAYS.**
> The record keeps its `items` rows (`line_id` + quantity), which go on feeding
> `approved_qty_by_line()` untouched, **and** gains the joint grid, which is what
> prints. `ra.py` is not modified by this pass. No existing test is rewritten or
> weakened. **§4.1 as written is withdrawn and is not to be re-applied from the
> brief.**
>
> **2. "There is exactly one live measurement record" — there are TWO.**
> `SF/MS/26-27/0001` (BOQ `SF/BOQ/26-27/0007`, project *Banglore*, 2 priced
> rows) and `SF/MS/26-27/0002` (BOQ `SF/BOQ/26-27/0008`, project *Sify
> Bangalore*, 87 priced rows and 10 headers, 5,865 measured). Neither is
> approved. The second is the larger record and the brief did not know it
> existed.
>
> **3. "Two accounts, not one" — the RA ladder needs THREE.** The brief's §2.3
> is right that the creator guard checks the record's creator and not the
> approver's role (`approval.can_approve()`, rule 4 — verified by reading, as
> that paragraph asked). But the RA ladder is **two rungs** (`operation-head`,
> `director`, unordered) and rule 5 — *one user, one rung* — stops a single
> approver climbing both. A creator plus **two** distinct approvers is the
> minimum, and the driver takes three accounts accordingly.
>
> **4. "Escalated rate == base × (1 + esc%)" is NOT an invariant of this repo.**
> The brief's §2.7 assertion 2 called it *"the definition the whole P&L rests
> on"*. `boq._derived_rate()` is explicit that it is **only ever a suggestion**
> and that the stored rate is whatever was entered, because the client's own
> sheets carry a dozen lines where the two disagree for a documented reason.
> The driver therefore pins the derivation only where it controls the input, and
> pins `amount == rate × qty` — which *is* enforced unconditionally — everywhere.
>
> #### The rulings behind the sheet — OURS, not the client's, and revisitable
>
> Every one of these is Manas's or ours. **None is a delivered CC-2
> requirement and nobody may later cite one as one.** They are listed so Yogesh
> can disagree with any of them individually.
>
> - **SITE is inherited, never typed.** It comes from the BOQ's project's
>   `site_address_id` with the label snapshotted at save, and falls back to what
>   the BOQ carries behind the existing amber drift band. Three spellings of one
>   city are already live in this database because site was free text in three
>   places; a fourth free-text site field would repeat the 30 August cleanup.
>   `SYSTEM`, `MATERIAL` and `AREA` are free text per sheet. `DIA METER` is free
>   text **and is not auto-filled** — the client's own sample reads *"25 mm To
>   150 mm"* while their grid carries a 200 NB column, so it is a stated scope
>   for the system and not a summary of the grid. A derived hint beside the
>   input lists which columns actually carry values.
>
> - **Columns and rows are DATA, not code.** The 12 numeric columns and 17
>   location rows are seeded exactly as the client's paper has them, but the
>   column definitions live in `/settings` in the same shape the charge heads
>   use, and rows may be added, renamed and removed per sheet. Their paper omits
>   15 NB and 20 NB while their BOQs have carried other diameters; a new site
>   with a different pipe schedule must not need a code change.
>
> - **⚠ The column set is SNAPSHOTTED onto the record at create.** A later
>   settings change must not restate an already-issued sheet. This is the same
>   invariant as the RA bill's own claim rows, and it has already shipped as a
>   defect once in this repo.
>
> - **Every column carries a unit** — metres for the dia columns, kg for MSA,
>   Nos for pendant and upright — and the unit prints in the head. A TOTAL row
>   that adds metres to kilograms is a lie the client's sheet currently tells
>   quietly.
>
> - **⚠ DELIBERATE DEPARTURE FROM THE CLIENT'S OWN ARITHMETIC.** Their workbook's
>   TOTAL row is wrong in three ways: `25 NB` has no total at all; an unlabelled
>   column immediately left of it *does*, and it sums rows 9–35 where every other
>   column sums 9–25; and `SUPPORTS (MSA kgs)` has no total either. **We total
>   every numeric column over every row and drop the unlabelled column.** This is
>   recorded so nobody later "fixes" it back to match their paper.
>
> - **No blank filler rows print.** Their paper form carries about ten ruled
>   blanks before the TOTAL row. The delivery challan pass already took this
>   decision on the argument that blank ruled rows underneath a signature invite
>   post-signature insertion, and **this document is countersigned by the
>   customer**, so the argument is stronger here than it was there.
>   ⚠ **Still needs Yogesh's confirmation**, exactly as the DC one still does.
>
> - **The right-hand sign-off party** comes from the BOQ's bill-to snapshot, and
>   the four label rows stay blank for a wet signature. Where the BOQ carries no
>   bill-to party the band prints **empty** rather than carrying an invented
>   placeholder.
>
> - **Both live records take the LEGACY BRANCH.** Neither carries per-row
>   location or diameter as structured data — `location` is a single free-text
>   field on the record, not a property of a row — so neither maps onto the grid
>   and migrating them would mean inventing data. They are marked old-model and
>   rendered through a legacy branch, the same treatment the day-rate migration
>   gave the one old employee record. **Nothing is deleted, nothing is reshaped,
>   and both stay in the register.**
>
> #### What this pass does NOT do
>
> **Gap 31 is not fixed.** `/boq/view` still compares a tax-exclusive subtotal
> against tax-inclusive RA `grand_total`s. The driver **asserts the disagreement
> is exactly the GST delta** and labels that line `KNOWN-BAD (gap 31)`, so the
> line flips to FAIL and tells us when somebody does fix it. Nothing here may be
> recorded as closing it.
>
> Also untouched: the `_nav()`-in-print-routes coupling, the shared table-helper
> refactor across 15 modules, and the linear "Measurement Sheet" shape from
> sheets 2 and 3 of the client's workbook — **the joint matrix is the document**,
> and both were not built.
>
> #### ⚠ THE DRIVER WRITES TO THE LIVE DEV DATABASE
>
> That is the whole reason it is worth having — 2,081 green tests run with
> `DB_ENABLED=false`, a cleared `STORE` and a tmpdir, and therefore say nothing
> about real MySQL, real sessions, real permission checks or real form posts.
> Three defects in this project's history were invisible to the suite and
> visible only in a browser. The containment is a dated backup pair taken before
> any write, a tagged run, a reverse-dependency-order teardown, and a dump diff
> against that backup.
>
> #### ⚠ THE DRIVER WAS NEVER RUN AGAINST THE LIVE DATABASE, and an authorisation was taken and NOT exercised
>
> **Added later on 6 September 2026, within the same pass and by the same
> person.** It is written into this block rather than into a new one because it
> records what this block's own work did and did not do; nothing above it has
> been edited.
>
> **Manas authorised the creation of three throwaway user accounts** — an Owner
> to create, an Operation Head and a Director to take one ladder rung each —
> so that `tools/e2e_chain.py` could be driven end to end against the running
> dev app. That is a **live identity mutation**, the class the fifth 29 August
> 2026 block says must be authorised on its own terms and may never cite a
> previous migration as precedent. It was authorised on its own terms, here.
>
> ⚠ **It was not exercised. No account was created, and no live record was
> written by this pass at all.** The orchestration was refused by the
> environment the agent runs in before it executed, and rather than work around
> that refusal the work stopped and was reported. So:
>
> - the authorisation **stands unused** and does not carry forward — a later
>   pass wanting those accounts needs its own;
> - **`STORE["users"]` and `STORE["roles"]` are untouched**, and so is every
>   document collection;
> - **`tools/backfill_measurement_grid.py` ships in this pass and has NOT been
>   run.** The two live measurement sheets carry no `grid_model` mark and
>   render legacy through its *absence*, which is correct behaviour but is not
>   the same fact as having been migrated, and the two must not be confused;
> - and **every one of the twelve tally assertions in the driver is
>   UNEXERCISED.** Its 63 offline helper tests pass and its seven mutations are
>   caught, which covers the arithmetic, the form parser and the teardown
>   ordering. **It covers none of the money.**
>
> **A driver reported as working on the strength of having been written is
> exactly what this block refuses to record.**
>
> #### Chargeability — unsettled, and left unsettled
>
> ⚠ **Both items are priced NOWHERE, and for different reasons.**
>
> **The driver** is test tooling for scope already sold; it is the closest thing
> in this pass to a §0 no-charge exemption, and it is still not recorded as one,
> because §0 exempts *defect and reachability fixes* and a new harness is
> neither.
>
> **The measurement sheet redesign** is not covered either. CC-2's C2 says
> nothing whatever about whether a measurement prints or what it looks like —
> the fifth block of 29 August 2026 already recorded that as ours, unspecced and
> unpriced, and this pass **replaces that unspecced layout with a different
> unspecced layout**. It does not become specified by being redrawn from the
> client's own workbook: a transcribed layout is evidence of what they use, not
> an instruction we were given or a thing they agreed to pay for.
>
> **No agent may invent a price for either, record either as delivered under
> either quotation, or record either as delivered no-charge.** Whether this is
> charged, absorbed or folded into a replacement quotation is a commercial
> decision the client-facing owner has not yet taken.
>
> #### Not a Phase 3 item, and the denominator is still 20
>
> ⚠ **Neither item is one of CC-2's twenty and neither may be counted toward
> them.** The board stays at **19 of 20 BUILT · 1 BLOCKED** — C6, still blocked
> on Open question 4, untouched by this pass. C2 was already BUILT before this
> pass and is still BUILT after it; **redrawing its printed sheet does not move
> it**, and the guards that make C2's own sentence true are deliberately
> unchanged.
>
> #### The gate is not lifted and this is not a precedent
>
> It stands, and it is still the default. **That this block authorises a test
> harness and a redrawn sheet does not authorise C6, does not answer CC-2's
> untagged lines 1 and 2, and does not authorise anything else.** An override is
> a decision the client-facing owner takes and records; it is never one an agent
> may take, infer, or extend.
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, everything built under the blocks above was
> built against a quotation that has **lapsed**.

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
commercial decision taken since, which is most of them. **Last updated 6 September
2026** — the most recent §0 block is the **end-to-end chain driver and the
JOINT MEASUREMENT SHEET** of that date, which also records that the brief for
that pass carried **four wrong premises**, the first of which would have deleted
two shipped guards and contradicted CC-2's C2. The block before it is the
**dashboard's BOQ/RA visual cues** of 5 September 2026, which records that a
*"Visual Dashboard is free, not chargeable"* ruling **was cited to that pass and
does not exist in this record**.** Phase 3 is a different meeting and a different file:
[CLIENT_CHANGES-2.md](CLIENT_CHANGES-2.md), 19 August 2026.*

*When an item's status changes, change it here and in [STATE.md](STATE.md) —
this file records the status, STATE.md orders the work. **When a dated block is
added to §0, update the date above in the same edit.***
