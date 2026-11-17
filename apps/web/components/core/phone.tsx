"use client";

import { Copy, Smartphone, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  ErrorBox,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";

type PhoneLink = { url: string; svg: string; problem: string | null };

/** Open DocuHive on a phone: scan the code, sign in, add it to the home screen. */
export function Phone() {
  const link = useApi<PhoneLink>("/api/system/phone");
  const [copied, setCopied] = useState(false);
  return (
    <Page narrow>
      <PageHeader
        title="On your phone"
        description="Photograph letters and receipts, or upload files from your phone, straight into DocuHive."
      />
      {link.error ? (
        <ErrorBox error={link.error} onRetry={link.reload} />
      ) : !link.data ? (
        <Skeleton rows={4} />
      ) : (
        <Card>
          <div className="flex flex-col gap-6 md:flex-row md:items-start">
            {/* eslint-disable-next-line @next/next/no-img-element -- generated locally, no remote image */}
            <img
              src={`data:image/svg+xml;utf8,${encodeURIComponent(link.data.svg)}`}
              alt={`QR code for ${link.data.url}`}
              width={200}
              height={200}
              className="mx-auto rounded-card border border-border bg-white p-2 md:mx-0"
            />
            <div className="min-w-0 space-y-3 text-sm">
              {link.data.problem && (
                <p role="alert" className="flex items-start gap-2 text-warning">
                  <TriangleAlert
                    aria-hidden="true"
                    className="mt-0.5 size-4 shrink-0"
                  />
                  <span>{link.data.problem}</span>
                </p>
              )}
              <ol className="list-decimal space-y-1.5 pl-5">
                <li>Connect the phone to your home Wi-Fi.</li>
                <li>
                  Open the camera and point it at the code, then tap the link.
                </li>
                <li>
                  The first time: trust the home certificate if the phone asks
                  (see the local network guide), then sign in with your own
                  account.
                </li>
                <li>
                  Add it to the home screen: iPhone: Share → Add to Home Screen.
                  Android: menu → Install app.
                </li>
                <li>Photograph pages or choose files, then upload.</li>
              </ol>
              <div className="flex flex-wrap items-center gap-2">
                <code className="break-all rounded bg-surface-2 px-2 py-1 text-xs">
                  {link.data.url}
                </code>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    void navigator.clipboard
                      .writeText(link.data!.url)
                      .then(() => setCopied(true))
                  }
                >
                  <Copy aria-hidden="true" />{" "}
                  {copied ? "Copied" : "Copy address"}
                </Button>
              </div>
              <p className="flex items-center gap-2 text-text-muted">
                <Smartphone aria-hidden="true" className="size-4" />
                Away from home it works only with remote access set up.
              </p>
            </div>
          </div>
        </Card>
      )}
    </Page>
  );
}
