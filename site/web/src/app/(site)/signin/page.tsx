import type { Metadata } from "next";
import { AuthForm } from "@/components/alerts/auth-form";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = { title: "Sign in | Tiresias", description: "Sign in to the local web app to receive slow-query alerts." };

export default function SignIn() {
  return (
    <Page>
      <H1>Sign in</H1>
      <AuthForm mode="signin" />
    </Page>
  );
}
