import type { Content } from "@/content/site";
import { Lead } from "../ui/lead";
import { Page } from "../ui/page";
import { Roster } from "../ui/roster";
import { Title } from "../ui/title";

// Who built the book; the title is where the landing's button lands.
export function Team({ name, disclaimer, title, lead, people }: Content["team"]) {
  return (
    <Page name={name} disclaimer={disclaimer} here="team" light={[0.78, 0.16]} place="centred" wide>
      <Title text={title} className="[view-transition-name:team]" />
      <Lead>{lead}</Lead>
      <Roster people={people} />
    </Page>
  );
}
