import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "react-toastify";

import { Input } from "../components/ui/Field";
import Button from "../components/ui/Button";
import { useForceLightTheme } from "../hooks/useForceLightTheme";

function ForgotPassword() {
  useForceLightTheme();

  const [email, setEmail] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email) {
      toast.error("Please enter your email address.");
      return;
    }
    // No password-reset endpoint exists in the backend yet — be honest about
    // that instead of pretending an email was sent.
    toast.info("Password reset isn't available yet. Please contact support to regain access to your account.");
  };

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-slate-50 dark:bg-slate-900 p-6">
      <div className="flex w-full max-w-4xl overflow-hidden rounded-2xl bg-white shadow-xl dark:bg-slate-800">

        {/* Brand panel — hidden below md, mirrors Login/Signup's split layout. */}
        <div className="hidden w-[46%] shrink-0 flex-col justify-center bg-gradient-to-br from-indigo-700 to-indigo-600 p-12 text-white md:flex">
          <div className="mb-7 flex h-12 w-12 items-center justify-center rounded-xl bg-white/15 text-sm font-bold">
            DT
          </div>
          <h2 className="max-w-[16ch] font-serif text-[26px] font-semibold leading-tight text-white">
            We'll help you get back into your Digital Twin.
          </h2>
          <p className="mt-4 max-w-[32ch] text-sm leading-relaxed text-white/75">
            Enter the email on your account and we'll walk you through regaining access.
          </p>
        </div>

        <div className="w-full shrink-0 p-8 sm:p-9 md:w-[380px]">
          <div className="mb-6">
            <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400">Digital Twin AI</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-800 dark:text-slate-100">Forgot Password</h1>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Enter your email to receive a reset link.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Email</label>
              <Input
                type="email"
                placeholder="Enter Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <Button type="submit" className="w-full">
              Send Reset Link
            </Button>
          </form>

          <p className="mt-6 text-center text-sm">
            <Link to="/login" className="font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
              Back to Login
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default ForgotPassword;
