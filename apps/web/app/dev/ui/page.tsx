import { notFound } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox } from "@/lib/ui/control";

export default function UI() {
  if (process.env.NODE_ENV === "production") notFound();
  return (
    <main className="p-6">
      <h1 className="mb-6 text-xl font-semibold">Interface controls</h1>
      <div data-testid="control-row" className="flex items-start gap-2">
        <Input aria-label="Text" placeholder="Text" />
        <Input aria-label="Date" type="date" />
        <Button type="button">Primary</Button>
        <Button type="button" variant="secondary">
          Secondary
        </Button>
      </div>
      <label className="mt-4 flex min-h-5 items-center gap-2 text-sm">
        <input className={checkbox} type="checkbox" />
        Form choice
      </label>
    </main>
  );
}
