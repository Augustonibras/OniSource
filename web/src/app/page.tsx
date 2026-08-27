"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

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
    <main className="flex min-h-screen items-center justify-center bg-brand-blue-50 px-6 py-12">
      <section className="w-full max-w-md rounded-2xl border border-brand-blue-300/50 bg-white px-8 py-10 shadow-[0_24px_70px_rgba(22,50,127,0.12)] sm:px-10">
        <div className="flex flex-col items-center text-center">
          <Image
            src="/onisource-symbol.svg"
            alt="Símbolo OniSource"
            width={80}
            height={80}
            priority
          />
          <h1 className="mt-5 text-3xl font-bold text-brand-blue-800">
            OniSource
          </h1>
          <p className="mt-2 text-sm uppercase tracking-widest text-gray-500">
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
              className="h-12 w-full rounded-lg border border-gray-300 bg-white px-4 text-gray-900 outline-none transition placeholder:text-gray-400 focus:border-brand-blue-700 focus:ring-4 focus:ring-brand-blue-300/40"
            />
            {errorMessage ? (
              <p id="email-error" className="mt-2 text-sm text-red-600">
                {errorMessage}
              </p>
            ) : null}
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="flex h-12 w-full items-center justify-center rounded-lg bg-brand-blue-800 px-4 font-semibold text-white transition-colors hover:bg-brand-blue-700 focus:outline-none focus:ring-4 focus:ring-brand-blue-300 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isLoading ? "Validando..." : "Entrar"}
          </button>
        </form>
      </section>
    </main>
  );
}
