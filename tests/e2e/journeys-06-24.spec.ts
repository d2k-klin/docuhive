import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { expect, type Page, test } from "@playwright/test";
import { CSRF, invoice, letter, signIn, stamp, store, stored } from "./helpers";

// Journeys about the machine room run once: they do not depend on the screen, and the
// outage one takes the vault away from every other test.
const ONCE = "runs once, in the 1280-light project";

const json = async (page: Page, path: string) =>
  (await page.request.get(path)).json();

const patch = (page: Page, id: string, data: object) =>
  page.request.patch(`/api/documents/${id}`, { headers: CSRF, data });

// The AI answers a few seconds after "stored"; these journeys need its runs finished.
async function analysed(page: Page, id: string) {
  await expect
    .poll(async () => {
      const queue = await json(page, `/api/review/queue?document_id=${id}`);
      return queue.items.length;
    }, stored)
    .toBeGreaterThan(0);
}

test("E2E-06 scanner folder, including a half-written file @J3 @CAP-03 @ING-05", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "1280-light", ONCE);
  test.setTimeout(300_000);
  await signIn(page, "alice");
  const marker = `scan${stamp().replace(/\W/g, "")}`;
  const name = `${info.project.name}-${Date.now()}.pdf`;
  const drop = (file: string, body: string | Buffer) =>
    execFileSync(
      "docker",
      [
        "compose",
        "-f",
        "deploy/compose.e2e.yml",
        "exec",
        "-T",
        "worker-ocr",
        "sh",
        "-c",
        `mkdir -p /srv/vault/consume/alice && cat > "/srv/vault/consume/alice/${file}"`,
      ],
      { input: body },
    );
  const listed = () =>
    execFileSync("docker", [
      "compose",
      "-f",
      "deploy/compose.e2e.yml",
      "exec",
      "-T",
      "worker-ocr",
      "ls",
      "/srv/vault/consume/alice",
    ]).toString();
  // A scanner still writing: the partial file must never be picked up.
  drop(`${name}.part`, "%PDF-1.4 half a pa");
  drop(name, letter(marker).buffer);
  // Meaning-based search also returns near matches; count the ones that hold the marker.
  const found = async () =>
    (await json(page, `/api/search?q=${marker}`)).filter(
      (hit: { snippet: string | null }) => hit.snippet?.includes(marker),
    );
  await expect
    .poll(async () => (await found()).length, { timeout: 240_000 })
    .toBe(1);
  // The scanned file is removed only after the stored original is verified; the partial stays.
  await expect.poll(listed, { timeout: 120_000 }).not.toContain(`${name}\n`);
  expect(listed()).toContain(`${name}.part`);
  expect(await found()).toHaveLength(1);
  await page.goto("/documents");
  await expect(page.getByRole("table")).toBeVisible();
});

test("E2E-07 upload-only token cannot read documents @smoke @J3 @CAP-04 @AUTH-02", async ({
  page,
  playwright,
}) => {
  await signIn(page, "alice");
  await page.goto("/settings/tokens");
  const name = `scanner-${stamp()}`;
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Retrieve knowledge-base chunks").uncheck();
  await page.getByLabel("Upload documents").check();
  const created = page.waitForResponse(
    (r) => r.url().endsWith("/api/tokens") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create token" }).click();
  const token = (await (await created).json()).token as string;
  // The secret is shown once, on the page, and listed by name afterwards.
  await expect(page.getByLabel("New API token")).toHaveValue(token);
  await expect(
    page.getByRole("region", { name: "Your tokens" }).getByText(name),
  ).toBeVisible();
  const api = await playwright.request.newContext({
    baseURL: test.info().project.use.baseURL,
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const upload = await api.post("/api/upload", {
    multipart: { files: letter("token upload") },
  });
  expect(upload.status()).toBe(202);
  const id = (await upload.json()).document_id;
  for (const path of [
    "/api/documents",
    `/api/documents/${id}`,
    `/api/documents/${id}/file?kind=original`,
    "/api/search?q=token",
    "/api/auth/me",
  ])
    expect((await api.get(path)).status(), path).toBe(403);
  await api.dispose();
});

test("E2E-08 edit, lock, history, re-run AI, unlock @J3 @DOC-03 @DOC-07", async ({
  page,
}) => {
  test.setTimeout(400_000);
  await signIn(page, "alice");
  const id = await store(page, invoice());
  await analysed(page, id);
  await page.goto(`/documents/${id}`);
  await page.getByRole("button", { name: "Edit" }).click();
  await page
    .getByRole("combobox", { name: "Category" })
    .selectOption("housing/rent");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(
    page.getByText("Saved. Your changes are locked against the AI."),
  ).toBeVisible();
  await expect(page.getByText("Rent & lease").first()).toBeVisible();
  const unlock = page.getByRole("button", {
    name: "Let the AI manage category",
  });
  await expect(unlock).toBeVisible();
  await expect(page.getByText(/You changed .*category/i)).toBeVisible();
  // Re-running the AI must not overwrite a locked field, whatever it suggests.
  const rerun = page.waitForResponse((r) =>
    r.url().endsWith("/api/review/reclassify"),
  );
  await page.getByRole("button", { name: "Re-run AI" }).click();
  expect((await rerun).ok()).toBe(true);
  await expect
    .poll(
      async () =>
        (await json(page, `/api/ai/runs?document_id=${id}`)).items.filter(
          (r: { task: string }) => r.task === "classify",
        ).length,
      stored,
    )
    .toBeGreaterThan(1);
  const doc = await json(page, `/api/documents/${id}`);
  expect(doc.category).toBe("housing/rent");
  expect(doc.manual_fields).toContain("category");
  // Handing the field back to the AI removes the lock.
  await page.reload();
  await unlock.click();
  await expect(unlock).toBeHidden();
  expect(
    (await json(page, `/api/documents/${id}`)).manual_fields,
  ).not.toContain("category");
});

test("E2E-09 bulk edit three documents @J3 @DOC-03 @DOC-07", async ({
  page,
}) => {
  test.setTimeout(400_000);
  await signIn(page, "alice");
  const tag = `bulk-${stamp()}`.toLowerCase();
  const ids = [];
  for (const n of [1, 2, 3])
    ids.push(await store(page, letter(`bulk edit ${n}`), { tags: tag }));
  await page.goto("/documents");
  await page.getByRole("textbox", { name: "Tag" }).fill(tag);
  await expect(page.getByRole("row")).toHaveCount(4); // header + 3
  await page.getByLabel("Select all on this page").check();
  const bar = page.getByRole("region", { name: "Edit selected documents" });
  await bar.getByLabel("Category").selectOption("purchases/receipts");
  await bar.getByLabel("Add tag").fill("bulk-done");
  await bar.getByRole("button", { name: "Apply to 3 documents" }).click();
  await expect(page.getByText("Updated 3 documents")).toBeVisible();
  for (const id of ids) {
    const doc = await json(page, `/api/documents/${id}`);
    expect(doc.category).toBe("purchases/receipts");
    expect(doc.tags).toEqual(expect.arrayContaining(["bulk-done", tag]));
    expect(doc.manual_fields).toEqual(
      expect.arrayContaining(["category", "tags"]),
    );
  }
});

test("E2E-10 search: word forms, accents, typos, filters, safe snippets @smoke @J3 @SRCH-01 @SRCH-03 @SRCH-04", async ({
  page,
}) => {
  test.setTimeout(400_000);
  await signIn(page, "alice");
  const key = `q${stamp().replace(/\W/g, "")}`;
  const id = await store(
    page,
    letter(
      `${key} Rechnung der Stadtwerke an Herrn Müller <script>alert("x")</script>`,
    ),
    { category: "utilities/electricity" },
  );
  // A date of its own keeps the archive's other documents out of the way: the checks
  // below are about matching, not about ranking in a growing archive.
  const day = `19${90 + Math.floor(Math.random() * 9)}-0${1 + Math.floor(Math.random() * 9)}-1${Math.floor(Math.random() * 9)}`;
  await patch(page, id, { document_date: day });
  const on = `date_from=${day}&date_to=${day}`;
  const hits = async (query: string) =>
    (await json(page, `/api/search?${query}`)).map(
      (hit: { document_id: string }) => hit.document_id,
    );
  // The search index follows an edit a moment later.
  for (const words of ["Rechnungen", "Muller", "Stadwerke"])
    await expect
      .poll(() => hits(`q=${words}&${on}`), { message: words, timeout: 60_000 })
      .toContain(id);
  expect(await hits(`q=${key}&category=utilities&${on}`)).toContain(id);
  expect(await hits(`q=${key}&category=finance&${on}`)).not.toContain(id);
  expect(await hits(`q=${key}&date_from=2026-01-01`)).not.toContain(id);
  // In the browser: highlighted, and the document's own markup is shown as text.
  let dialogs = 0;
  page.on("dialog", (dialog) => {
    dialogs++;
    void dialog.dismiss();
  });
  await page.goto("/search");
  await page.getByLabel("Search your documents").fill(`${key} Stadtwerke`);
  await page.getByRole("button", { name: "Search" }).click();
  const results = page.getByRole("list", { name: "Results" });
  await expect(results.locator(`a[href="/documents/${id}"]`)).toBeVisible();
  await expect(results.locator("mark").first()).toBeVisible();
  expect(await results.locator("script").count()).toBe(0);
  expect(dialogs).toBe(0);
});

test("E2E-11 similar documents @J4 @SRCH-05", async ({ page }) => {
  test.setTimeout(400_000);
  await signIn(page, "alice");
  // The same letter twice (different files, identical text) are each other's nearest match.
  const original = letter("Mietvertrag Anlage zur Nebenkostenabrechnung");
  const first = await store(page, original);
  const second = await store(page, {
    ...original,
    buffer: Buffer.concat([original.buffer, Buffer.from("\n%copy\n")]),
  });
  await analysed(page, first);
  await analysed(page, second);
  await expect
    .poll(
      async () =>
        (await json(page, `/api/ai/similar/${first}`)).items.map(
          (hit: { id: string }) => hit.id,
        ),
      stored,
    )
    .toContain(second);
  await page.goto(`/documents/${first}`);
  await expect(
    page.locator(`main a[href="/documents/${second}"]`).first(),
  ).toBeVisible();
});

test("E2E-19 multi-user isolation, then sharing @J5 @AUTH-03 @QA-06", async ({
  page,
  browser,
}) => {
  test.setTimeout(400_000);
  const marker = `bobsecret${stamp().replace(/\W/g, "")}`;
  await signIn(page, "bob");
  const id = await store(page, letter(`${marker} private note`), {
    shared: "false",
  });
  await analysed(page, id);
  await patch(page, id, {
    facts: { due_date: { type: "date", value: "2031-01-31" } },
  });

  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    baseURL: test.info().project.use.baseURL,
  });
  const alice = await context.newPage();
  await signIn(alice, "alice");
  const hidden = async () => {
    for (const path of [
      `/api/documents/${id}`,
      `/api/documents/${id}/file?kind=original`,
      `/api/documents/${id}/file?kind=archive`,
      `/api/documents/${id}/thumbnail`,
      `/api/documents/${id}/history`,
      `/api/ai/similar/${id}`,
    ])
      expect((await alice.request.get(path)).status(), path).toBe(404);
    for (const path of [
      "/api/documents?limit=200",
      `/api/search?q=${marker}`,
      `/api/ai/semantic-search?q=${marker}`,
      "/api/review/queue",
      "/api/reminders",
      "/api/duplicates",
      "/api/ai/runs?limit=200",
    ]) {
      const response = await alice.request.get(path);
      expect(response.ok(), path).toBe(true);
      const body = await response.text();
      expect(body, path).not.toContain(marker);
      expect(body, path).not.toContain(id);
    }
    expect((await patch(alice, id, { title: "taken over" })).status()).toBe(
      404,
    );
  };
  await hidden();
  await alice.goto("/search");
  await alice.getByLabel("Search your documents").fill(marker);
  await alice.getByRole("button", { name: "Search" }).click();
  // Meaning-based search may list near matches; none of them is Bob's document.
  await expect(
    alice
      .getByRole("list", { name: "Results" })
      .or(alice.getByText(/Nothing found/)),
  ).toBeVisible();
  await expect(alice.locator(`a[href="/documents/${id}"]`)).toHaveCount(0);
  await expect(alice.getByRole("main")).not.toContainText(marker.slice(0, 40));

  // Bob shares it: Alice can read it, and still cannot change it.
  expect((await patch(page, id, { shared: true })).ok()).toBe(true);
  await alice.goto(`/documents/${id}`);
  await expect(alice.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(alice.getByRole("button", { name: "Edit" })).toBeHidden();
  expect(
    (await alice.request.get(`/api/search?q=${marker}`)).ok() &&
      (await (await alice.request.get(`/api/search?q=${marker}`)).text()),
  ).toContain(id);
  expect([403, 404]).toContain(
    (await patch(alice, id, { title: "taken over" })).status(),
  );
  // Shared documents show in everyone's review queue; leave the archive as it was found.
  await page.request.post(`/api/documents/${id}/trash`, { headers: CSRF });
  await context.close();
});

test("E2E-20 quarantine: unreadable files, reason, retry @J3 @ING-04 @ING-06", async ({
  page,
}) => {
  test.setTimeout(400_000);
  await signIn(page, "alice");
  const broken = {
    name: `broken-${stamp()}.pdf`,
    mimeType: "application/pdf",
    buffer: Buffer.from(`%PDF-1.7\n${stamp()} this is not a real PDF\n%%EOF\n`),
  };
  const id = await store(page, broken, {}, "quarantined"); // after its retries
  await page.goto("/quarantine");
  const row = page
    .getByRole("listitem")
    .filter({ hasText: broken.name.replace(".pdf", "") });
  await expect(row).toBeVisible();
  // A plain-language reason, never a stack trace or an exception name.
  await expect(row).not.toContainText(/Error|Exception|Traceback/);
  // The upload is kept, so it can be read again.
  await row.getByRole("button", { name: /Retry|Try again/ }).click();
  await expect(page.getByText("Sent for reading again.")).toBeVisible();
  expect((await json(page, `/api/documents/${id}`)).status).not.toBe("stored");
  // An unsupported file is refused at the door with a reason, not stored half-way.
  await page.goto("/upload");
  await page.getByLabel("Choose files to upload").setInputFiles({
    name: "program.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from([0, 159, 146, 150, 1, 2, 3, 4, 5, 6, 7, 8]),
  });
  await expect(
    page.getByRole("listitem").filter({ hasText: "program.bin" }),
  ).toContainText(/not supported|Needs attention|failed/i, stored);
});

const compose = (...args: string[]) =>
  execFileSync("docker", ["compose", "-f", "deploy/compose.e2e.yml", ...args]);

async function ask(page: Page, question: string) {
  await page.getByLabel("Your question").fill(question);
  const answered = page.waitForResponse(
    (r) => /\/api\/chat\/sessions\/[^/]+\/messages$/.test(r.url()) && r.ok(),
  );
  await page.getByRole("button", { name: "Send" }).click();
  await (await answered).finished();
}

test("E2E-12 ask for a total: facts table, computed total, citations @smoke @J4 @QA-01 @QA-02 @QA-03", async ({
  page,
}) => {
  test.setTimeout(400_000);
  await signIn(page, "alice");
  const id = await store(page, invoice(), {
    category: "utilities/electricity",
  });
  // The amount is suggested a moment after the category; accept until it is a fact.
  await expect(async () => {
    await page.request.post(`/api/review/documents/${id}/accept-all`, {
      headers: CSRF,
    });
    const doc = await json(page, `/api/documents/${id}`);
    expect(doc.facts.amount_total?.value).toBe("84.20");
  }).toPass(stored);
  await page.goto("/ask");
  await ask(page, "How much did I spend on electricity in 2025?");
  const main = page.getByRole("main");
  await expect(main.getByText("What I did: Queried facts")).toBeVisible();
  // The numbers come from SQL over accepted facts, not from the model.
  const table = main.getByRole("table").last();
  await expect(table.locator(`a[href="/documents/${id}"]`)).toBeVisible();
  const total = await table.locator("tfoot tr").first().innerText();
  const count = Number(total.match(/Total \((\d+)\)/)![1]);
  expect(count).toBeGreaterThan(0);
  expect(total.replace(/[^\d]/g, "")).toContain(
    (count * 84.2).toFixed(2).replace(".", ""),
  );
  // The answer cites its documents, so there is no "cites no documents" warning.
  await expect(
    main
      .locator(`p a[href="/documents/${id}"], li a[href="/documents/${id}"]`)
      .first(),
  ).toBeVisible();
  await expect(main.getByText("This answer cites no documents")).toBeHidden();
});

test("E2E-13 a question handed over to Ask @J4 @QA-07", async ({ page }) => {
  await signIn(page, "alice");
  const question = `where is the ${stamp()} certificate`;
  // Search hands a question over as /ask?q=…; with meaning-based search on, its "Ask instead"
  // link only shows when nothing at all matches, so the journey starts at the hand-over.
  await page.goto(`/ask?q=${encodeURIComponent(question)}`);
  await expect(page.getByLabel("Your question")).toHaveValue(question);
  const answered = page.waitForResponse(
    (r) => /\/api\/chat\/sessions\/[^/]+\/messages$/.test(r.url()) && r.ok(),
  );
  await page.getByRole("button", { name: "Send" }).click();
  await (await answered).finished();
  await expect(
    page.getByRole("main").getByText("I could not find matching documents"),
  ).toBeVisible();
});

test("E2E-14 ask with no results, and chat history @J4 @QA-02 @QA-07", async ({
  page,
}) => {
  await signIn(page, "alice");
  await page.goto("/ask");
  const question = `Where is my passport ${stamp()}?`;
  await ask(page, question);
  const main = page.getByRole("main");
  // No invented answer: guidance, no document links, and nothing presented as a fact.
  await expect(
    main.getByText("I could not find matching documents. Try broader dates."),
  ).toBeVisible();
  await expect(main.getByRole("table")).toHaveCount(0);
  await expect(main.locator('p a[href^="/documents/"]')).toHaveCount(0);
  // The chat is kept and can be reopened.
  await page.reload();
  await page
    .getByRole("complementary", { name: "Chats" })
    .getByRole("button", { name: question })
    .click();
  await expect(
    main.getByText("I could not find matching documents. Try broader dates."),
  ).toBeVisible();
});

for (const [id, title, blocker] of [
  [
    "E2E-15",
    "Gmail connect, backfill, rerun, pause and resume @J2 @MAIL-01 @MAIL-02 @MAIL-03 @MAIL-06 @MAIL-09",
    "Gmail's endpoints cannot be pointed at the mock",
  ],
  [
    "E2E-16",
    "Outlook and IMAP incremental sync with triage @J2 @MAIL-04 @MAIL-05 @MAIL-07 @MAIL-08 @MAIL-10",
    "Graph's endpoints cannot be pointed at the mock, and the stack has no IMAP server",
  ],
  [
    "E2E-17",
    "revoked mail token, needs sign-in again, reconnect @J2 @GUIDE-04",
    "needs a connected mock mailbox first",
  ],
] as const)
  test(`${id} ${title}`, async ({ page }) => {
    test.fixme(true, `${blocker}: docs/Developer-QA/bugs.md#qa-005`);
    await signIn(page, "alice");
    await page.goto("/sources");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

test("E2E-18 restricted documents never reach a cloud model @smoke @J5 @AI-03 @NFR-01", async ({
  page,
}) => {
  test.setTimeout(400_000);
  await signIn(page, "alice");
  const marker = `bloodwork${stamp().replace(/\W/g, "")}`;
  const id = await store(
    page,
    letter(`Medical report\n${marker} confidential`),
    {
      category: "health",
      shared: "false",
    },
  );
  await expect
    .poll(
      async () =>
        (await json(page, `/api/ai/runs?document_id=${id}`)).items.length,
      stored,
    )
    .toBeGreaterThan(1);
  // Every AI run on a restricted document used a local model.
  const runs = (await json(page, `/api/ai/runs?document_id=${id}`)).items;
  for (const run of runs)
    expect(run, `${run.task} run`).toMatchObject({
      restricted: true,
      local: true,
    });

  await page.goto("/ask");
  const model = page.getByRole("combobox", { name: "Model" });
  // Asked through the cloud route, the document is not found, cited or sent.
  await model.selectOption({ label: "qacloud/qa-chat-cloud" });
  await ask(page, "What does my medical report say?");
  const main = page.getByRole("main");
  await expect(main.getByText("What I did:").last()).toBeVisible();
  // Asked through the local route, the same question finds and cites it.
  await page.getByRole("button", { name: "New chat" }).click();
  await model.selectOption({ label: "qa/qa-chat (local)" });
  await ask(page, "What does my medical report say?");
  await expect(
    main.locator(`a[href="/documents/${id}"]`).first(),
  ).toBeVisible();
  // What actually left for the cloud-flagged model, as recorded by the capturing proxy.
  const calls = await (
    await page.request.get("https://127.0.0.1:58001/__calls")
  ).json();
  const cloud = calls.filter(
    (call: { model: string }) => call.model === "qa-chat-cloud",
  );
  expect(cloud.length).toBeGreaterThan(0);
  // The cloud model may learn that a restricted document matched, and nothing about it.
  for (const call of cloud)
    expect(JSON.stringify(call.body)).not.toContain(marker);
  expect(JSON.stringify(cloud)).toContain("[restricted]");
  expect(
    calls.some((call: { body: object }) =>
      JSON.stringify(call.body).includes(marker),
    ),
  ).toBe(true); // the local route did read it, so the check above is not vacuous
});

test("E2E-21 storage outage: warning, nothing lost, recovery @J5 @STO-05 @GUIDE-02", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "1280-light", ONCE);
  test.setTimeout(300_000);
  await signIn(page, "alice");
  const vault = (...command: string[]) =>
    compose("exec", "-T", "worker-ocr", ...command).toString();
  // An unmounted share looks like a folder without the vault's identity.
  vault("mv", "/srv/vault/_system", "/srv/vault/_system.away");
  try {
    const before = vault("ls", "/srv/vault");
    const response = await page.request.post("/api/upload", {
      headers: CSRF,
      multipart: { files: letter("uploaded during the outage") },
    });
    expect(response.status()).toBe(202);
    const id = (await response.json()).document_id as string;
    await expect
      .poll(async () => {
        const checks = await json(page, "/api/system/setup-status");
        return checks.find((c: { id: string }) => c.id === "vault").status;
      }, stored)
      .toBe("error");
    await page.goto("/");
    await expect(
      page
        .getByText(
          /No DocuHive vault was found|Storage is unavailable|not reachable/,
        )
        .first(),
    ).toBeVisible();
    await expect(
      page.getByText("Connect your storage (Problem)"),
    ).toBeVisible();
    // The upload waits in staging; nothing is written into the bare folder.
    await page.waitForTimeout(20_000);
    expect((await json(page, `/api/documents/${id}`)).status).toBe("staged");
    expect(vault("ls", "/srv/vault")).toBe(before);
    vault("mv", "/srv/vault/_system.away", "/srv/vault/_system");
    await expect
      .poll(async () => (await json(page, `/api/documents/${id}`)).status, {
        timeout: 200_000,
      })
      .toBe("stored");
    await page.reload();
    await expect(page.getByText("Connect your storage (Done)")).toBeVisible();
  } finally {
    try {
      vault("mv", "/srv/vault/_system.away", "/srv/vault/_system");
    } catch {
      /* already back */
    }
  }
});

test("E2E-22 database lost, rebuilt from the vault @J5 @STO-04 @NFR-03", async ({
  page,
}) => {
  test.fixme(
    true,
    "Dropping the database would take the shared journey stack down. The drill runs on its own stack in services/docuhive/tests/core/test_operations_integration.py",
  );
  await signIn(page, "alice");
  compose("exec", "-T", "api", "docuhive", "vault", "rebuild");
});

test("E2E-23 a due date becomes a reminder and a calendar entry @J5 @QA-05 @AUTO-03", async ({
  page,
  playwright,
}) => {
  test.setTimeout(400_000);
  await signIn(page, "alice");
  const id = await store(page, invoice());
  await analysed(page, id);
  const due = new Date(Date.now() + 40 * 86_400_000).toISOString().slice(0, 10);
  expect(
    (
      await patch(page, id, {
        title: `Reminder ${stamp()}`,
        document_type: "invoice",
        facts: { due_date: { type: "date", value: due } },
      })
    ).ok(),
  ).toBe(true);
  const mine = async () =>
    (await json(page, "/api/reminders")).items.filter(
      (r: { document_id: string }) => r.document_id === id,
    );
  await expect.poll(async () => (await mine()).length, stored).toBe(1);
  expect((await mine())[0].due_on).toBe(due);
  await page.goto("/reminders");
  await expect(
    page.locator(`main a[href="/documents/${id}"]`).first(),
  ).toBeVisible();
  // The calendar feed needs its own token, and that token opens nothing else.
  const created = await page.request.post("/api/tokens", {
    headers: CSRF,
    data: { name: `calendar-${stamp()}`, scopes: ["calendar"] },
  });
  const token = (await created.json()).token as string;
  const api = await playwright.request.newContext({
    baseURL: test.info().project.use.baseURL,
    ignoreHTTPSErrors: true,
  });
  const feed = await api.get(`/api/reminders.ics?token=${token}`);
  expect(feed.ok()).toBe(true);
  const calendar = await feed.text();
  expect(calendar).toContain("BEGIN:VEVENT");
  expect(calendar).toContain(due.replaceAll("-", ""));
  expect(
    (
      await api.get("/api/documents", {
        headers: { Authorization: `Bearer ${token}` },
      })
    ).status(),
  ).toBe(403);
  expect((await api.get("/api/reminders.ics?token=wrong")).status()).toBe(401);
  await api.dispose();
});

test("E2E-24 saved analysis, and how an AI value was made @J4 @QA-04 @LRN-03 @LRN-04", async ({
  page,
}) => {
  test.setTimeout(400_000);
  await signIn(page, "alice");
  const id = await store(page, invoice());
  await analysed(page, id);
  const name = `Utilities by month ${stamp()}`;
  await page.request.post("/api/analyses", {
    headers: CSRF,
    data: {
      name,
      prompt:
        "Sum amount_total of invoices in the utilities category for this year, by month.",
    },
  });
  await page.goto("/analyses");
  const saved = page.getByRole("button", { name: new RegExp(`^${name} `) });
  await saved.click();
  const ran = page.waitForResponse((r) =>
    /\/api\/analyses\/\d+\/run$/.test(r.url()),
  );
  await page.getByRole("button", { name: "Run", exact: true }).click();
  expect((await ran).ok()).toBe(true);
  const result = page
    .getByRole("main")
    .getByText("I could not find matching documents");
  await expect(result).toBeVisible(stored);
  // The result is saved with the analysis.
  await page.reload();
  await saved.click();
  await expect(result).toBeVisible();
  // From a value the AI set, one click shows which model, prompt and cost produced it.
  await page.goto(`/documents/${id}`);
  await page
    .getByRole("link", { name: /how was this made\?/ })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "How was this made?" }),
  ).toBeVisible();
  for (const term of ["Model", "Prompt", "Privacy", "Tokens", "Cost", "Time"])
    await expect(
      page.getByRole("term").filter({ hasText: term }).first(),
    ).toBeVisible();
  const learn = await page
    .getByRole("link", { name: "Learn how this works" })
    .getAttribute("href");
  expect(existsSync(learn!.replace(/^.*\/blob\/main\//, ""))).toBe(true);
});
