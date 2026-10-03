import type { Metadata } from "next";
import { H1, H2, P } from "@/components/site/prose";

export const metadata: Metadata = { title: "Terms of use | Blind Tuner", description: "Terms for this website: a hackathon prototype, no warranty, code under the MIT License." };

// Ported from site/src/terms.html. Needs human review before deploy.
export default function Terms() {
  return (
    <article className="glass rounded-xl p-6">
      <H1>Terms of use for this website</H1>
      <P>Last updated 4 October 2026.</P>
      <H2>The site describes a hackathon prototype</H2>
      <P>This website describes Blind Tuner, an entry built for the CodeUtsava X.0 hackathon, Problem Statement 4. It is information about a prototype, not a product or a service. Nothing on it is an offer to provide software, support or advice.</P>
      <H2>Results apply to the demo database only</H2>
      <P>Every number on this site was measured on a synthetic demo database on one machine, under the assumptions printed next to it. It does not predict what Blind Tuner would do on another database, and it is not a benchmark.</P>
      <H2>No warranty</H2>
      <P>The site and its content are provided as they are, without warranty of any kind. Use them at your own risk. The authors are not liable for any loss arising from use of the site or reliance on its content.</P>
      <H2>Source code is governed by its repository</H2>
      <P>These terms cover this website only. The source code is released under the MIT License, set out in the LICENSE file of its repository at <a className="text-blue-700 underline" href="https://github.com/Derpinator96/Tiresias">github.com/Derpinator96/Tiresias</a>. That license, not this page, governs use of the code.</P>
      <H2>Changes</H2>
      <P>These terms may change. The date at the top shows the latest version.</P>
    </article>
  );
}
