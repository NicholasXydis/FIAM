import type { Content } from "@/content/site";
import { Button } from "../ui/button";
import { Lead } from "../ui/lead";
import { Page } from "../ui/page";
import { Title } from "../ui/title";

// Not found: one light in the dark, one sentence, one way home.
export function Missing({ name, disclaimer, title, lead }: Content["missing"]) {
  return (
    <Page name={name} disclaimer={disclaimer} here="missing" light={[0.5, 0.24]} place="centred">
      <Title text={title} />
      <Lead>{lead}</Lead>
      <nav aria-label="Way back" className="mt-[calc(var(--spacing-flow)*0.4)] flex justify-center">
        <Button href="/">Back to home</Button>
      </nav>
    </Page>
  );
}
