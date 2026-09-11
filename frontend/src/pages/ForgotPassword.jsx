import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "react-toastify";

import { Input } from "../components/ui/Field";
import Button from "../components/ui/Button";
import { useForceLightTheme } from "../hooks/useForceLightTheme";
import SilkBackground from "../components/SilkBackground";
import SplitHeading from "../components/ui/SplitHeading";

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
    <div className="flex min-h-screen w-full bg-white dark:bg-slate-800">

      {/* Brand panel — hidden below md so the form stays full-width and
          uncluttered on phones, mirrors Login/Signup's split layout exactly
          (full window height on its half, not a centered card). */}
      <div className="relative hidden w-1/2 shrink-0 flex-col justify-center overflow-hidden bg-gradient-to-br from-indigo-700 to-indigo-600 px-16 text-white md:flex">
        <SilkBackground />
        <div className="relative z-10">
          <img
            src="/logo-icon.png"
            alt="Digital Twin AI"
            className="mb-7 h-28 w-28 object-contain drop-shadow-[0_0_16px_rgba(255,255,255,0.55)]"
          />
          <h2 className="max-w-[18ch] font-serif text-[32px] font-semibold leading-tight text-white">
            Get back into your account.
          </h2>
          <p className="mt-4 max-w-[36ch] text-[15px] leading-relaxed text-white/75">
            Enter the email on your account and we'll help you regain access.
          </p>
        </div>
      </div>

      <div className="flex w-full flex-1 items-center justify-center overflow-y-auto p-6">
        <div className="w-full max-w-sm">

          <div className="mb-6">
            <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400">
              Digital Twin AI
            </p>

            <SplitHeading
              as="h1"
              text="Forgot Password"
              className="mt-2 text-2xl font-semibold text-slate-800 dark:text-slate-100"
            />

            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Enter your email to receive a reset link.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">
                Email
              </label>
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

          <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
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
