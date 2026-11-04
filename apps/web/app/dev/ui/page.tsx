import { notFound } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

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
    </main>
  );
}
