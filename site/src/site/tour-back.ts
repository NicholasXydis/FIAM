// The tour's Back: the site's pill, wired without React to stay light.
import "./ui/pill.css";
import "./tour-back.css";
import { goBack } from "./ui/back";
import { afterPress, plain, wirePill } from "./ui/press";

// The Back pill the build put in this page, if there is one.
const pill = document.querySelector<HTMLAnchorElement>(".tour-back");
// Make it press like the site's pills and step back on a click.
if (pill) {
  wirePill(pill);
  // Back to the site page before, or home when the tour was opened cold.
  pill.addEventListener("click", (e) => {
    if (!plain(e)) return;
    e.preventDefault();
    afterPress(() => goBack());
  });
}
