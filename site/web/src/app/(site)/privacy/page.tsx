import type { Metadata } from "next";
import { H1, H2, P } from "@/components/site/prose";

export const metadata: Metadata = { title: "Privacy policy | Blind Tuner", description: "What this website collects: nothing itself; the host keeps request logs." };

// Ported from site/src/privacy.html and updated for the Next.js site. Needs human review before deploy.
export default function Privacy() {
  return (
    <article className="glass rounded-xl p-6">
      <H1>Privacy policy for this website</H1>
      <P>Last updated 4 October 2026. This policy covers this website only, not the Blind Tuner software.</P>
      <H2>This site collects nothing itself</H2>
      <P>The site has no accounts, no forms that send anything, no comments, no cookies, no analytics and no tracking pixels. Its scripts and fonts are served from this site&apos;s own address; it loads nothing from other servers. It has no connection to any database and never receives the demo database or any data from it.</P>
      <H2>The hashing visualizer runs in your browser</H2>
      <P>The text you type into the hashing visualizer and the demo key it generates stay in your browser tab. Nothing is sent anywhere, and both are gone when you close or reload the page.</P>
      <H2>The hosting provider processes request data</H2>
      <P>The site is hosted on Vercel. To deliver pages and protect the service, Vercel receives standard request information, such as your IP address, browser user agent and the page requested, and may keep it in logs. Vercel handles that data under its own privacy policy: <a className="text-blue-700 underline" href="https://vercel.com/legal/privacy-policy">vercel.com/legal/privacy-policy</a>. We do not receive those logs unless we look at them in the hosting dashboard, and we do not combine them with anything else.</P>
      <H2>Numbers on this site come from synthetic data</H2>
      <P>Every measurement shown comes from a demo database generated for this project. It holds no real person&apos;s data.</P>
      <H2>Contact</H2>
      <P>Questions about this policy: open an issue at <a className="text-blue-700 underline" href="https://github.com/Derpinator96/Tiresias/issues">github.com/Derpinator96/Tiresias/issues</a>.</P>
    </article>
  );
}
