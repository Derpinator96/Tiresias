import type { Metadata } from "next";
import { AuthForm } from "@/components/alerts/auth-form";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = { title: "Create account | Tiresias", description: "Create a local account; slow-query alerts are emailed to its address." };

export default function SignUp() {
  return (
    <Page>
      <H1>Create account</H1>
      <AuthForm mode="signup" />
    </Page>
  );
}
