"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AlertCircle } from "lucide-react";

import { supabase } from "../lib/supabase";

const SESSION_KEY = "onisource_session";
const UNAUTHORIZED_MESSAGE =
  "Email não autorizado. Solicite acesso ao administrador.";

export default function Home() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");
    setIsLoading(true);

    const normalizedEmail = email.trim().toLowerCase();
    const { data, error } = await supabase
      .from("allowed_emails")
      .select("role")
      .eq("email", normalizedEmail)
      .limit(1);

    if (error || !data?.[0]) {
      setErrorMessage(UNAUTHORIZED_MESSAGE);
      setIsLoading(false);
      return;
    }

    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ email: normalizedEmail, role: data[0].role }),
    );
    router.push("/search");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#F8F9FC] px-6 py-12">
      <section className="w-full max-w-md rounded-xl border border-gray-200 bg-white px-8 py-10 shadow-sm sm:px-10">
        <div className="flex flex-col items-center text-center">
          <Image
            src="/onisource-symbol.svg"
            alt="Símbolo OniSource"
            width={72}
            height={72}
            priority
          />
          <h1 className="mt-5 text-2xl font-semibold text-[#16327F]">
            OniSource
          </h1>
          <p className="mt-2 text-xs uppercase tracking-[0.2em] text-gray-500">
            Inteligência de Sourcing
          </p>
        </div>

        <form onSubmit={handleSubmit} className="mt-9 space-y-5">
          <div>
            <label htmlFor="email" className="sr-only">
              Email corporativo
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="Seu email corporativo"
              aria-invalid={Boolean(errorMessage)}
              aria-describedby={errorMessage ? "email-error" : undefined}
              className="h-12 w-full rounded-lg border border-gray-300 bg-white px-4 text-gray-900 outline-none transition placeholder:text-gray-400 focus:border-[#2B4FAE] focus:ring-1 focus:ring-[#2B4FAE]"
            />
            {errorMessage ? (
              <p id="email-error" className="mt-2 flex items-start gap-2 text-sm text-red-600">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{errorMessage}</span>
              </p>
            ) : null}
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="flex h-12 w-full items-center justify-center rounded-lg bg-[#16327F] px-4 font-medium text-white transition-colors hover:bg-[#2B4FAE] focus:outline-none focus:ring-2 focus:ring-[#85A3E3] disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isLoading ? "Validando..." : "Entrar"}
          </button>
        </form>
      </section>
    </main>
  );
}
