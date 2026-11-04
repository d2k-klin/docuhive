# Knowledge bases and API tokens

A knowledge base saves a set of document filters. It uses the existing archive and
index; it does not duplicate your files. Open **Knowledge bases** in the navigation
and choose **Create knowledge base**. Enter a name, choose categories, types, tags,
sources or dates, and save. Leaving a field empty includes all values in that field.

Suggested scopes appear only when you have documents. They offer Everything and
top-level categories found in your visible documents. Nothing is created silently.

## Sharing and privacy

Sharing a knowledge base lets other users see the saved scope. It does not share
private documents. Each user gets results only from documents they already own or
can access. Only the knowledge-base owner can change or delete the scope. Deleting
a scope keeps its documents and chunks.

**Use local AI only** asks the answer service to use local models. Turning it off
still preserves restricted-category and tag privacy rules.

## Indexing status

- **Documents:** stored, visible documents matching the saved filters.
- **Indexed:** documents with at least one embedded chunk.
- **Pending:** documents with no chunks and no terminal embedding failure, or a
  queued/running embedding job.
- **Failed:** documents whose latest embedding job failed permanently.
- **Stale:** documents containing chunks from an older embedding model.

Counts can overlap: a document can remain indexed while a replacement is pending,
failed or stale. Changing a saved filter does not start indexing. The embedding
model turns text into numbers so the archive can be searched by meaning. The page
shows the model currently selected in routing and the latest chunk creation time.

## Connect an app or agent

Open **API tokens**, give the token a recognisable name and select only the access
the app needs. **Retrieve knowledge-base chunks** uses `kb:read`; **Ask knowledge
bases** uses `kb:ask`. Copy the token when it is created: the server stores only its
hash and cannot show the secret again. Revoke a token to stop its app's access.

Leave **Local-only consumer** off for apps that may send results outside your
network. Enable it only for an app you trust to keep retrieved text local. It permits
the retrieval service to include restricted documents you can already access.
The flag records your trust decision; it cannot control what another app does
after receiving text. Bearer tokens cannot create a new token with this flag.

The saved-scope manager and token settings are available independently of the
retrieval/Ask APIs and MCP transport. Check the [implementation status](../Developer-OA/STATUS.md)
and [knowledge-base plan](../shared/knowledge-bases.md) before connecting a client.
