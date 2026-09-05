import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import { Eye, EyeOff } from "lucide-react";

import { loginUser } from "../services/authService";
import { useAuth } from "../context/useAuth";
import { useForceLightTheme } from "../hooks/useForceLightTheme";
import { Input } from "../components/ui/Field";
import Button from "../components/ui/Button";
import { getApiErrorMessage } from "../utils/apiError";

// Only the email is ever remembered — never the password. localStorage is
// readable by any JavaScript on the page (XSS, a malicious extension, etc.),
// so storing a raw password there would hand out reusable, non-expiring
// credentials to anything that can run script on this origin. Pre-filling
// the email is the standard, safe version of "Remember Me"; the password
// still has to be typed every time.
const REMEMBER_ME_KEY = "digital_twin_remember_me";

function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  useForceLightTheme();

  const savedEmail = (() => {
    try {
      return localStorage.getItem(REMEMBER_ME_KEY) || "";
    } catch {
      return "";
    }
  })();

  const [formData, setFormData] = useState({
    email: savedEmail,
    password: "",
  });

  const [rememberMe, setRememberMe] = useState(!!savedEmail);
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleRememberMeChange = (e) => {
    const checked = e.target.checked;
    setRememberMe(checked);

    // If the user turns Remember Me off, remove saved credentials.
    if (!checked) {
      localStorage.removeItem(REMEMBER_ME_KEY);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      // Save (or clear) only the email — never the password.
      if (rememberMe) {
        localStorage.setItem(REMEMBER_ME_KEY, formData.email);
      } else {
        localStorage.removeItem(REMEMBER_ME_KEY);
      }

      const data = await loginUser(formData);
      await login(data);

      navigate("/dashboard");
    } catch (err) {
      toast.error(
        getApiErrorMessage(
          err,
          "Invalid email or password. Please try again."
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen w-full bg-white dark:bg-slate-800">

      {/* Brand panel — hidden below md so the form stays full-width and
          uncluttered on phones, per the redesign concept's split layout.
          Fills the full window height on its half rather than floating as a
          centered card, so the page always fills the browser window. */}
      <div className="hidden w-1/2 shrink-0 flex-col justify-center bg-gradient-to-br from-indigo-700 to-indigo-600 px-16 text-white md:flex">
        <div className="mb-7 flex h-12 w-12 items-center justify-center rounded-xl bg-white/15 text-sm font-bold">
          DT
        </div>
        <h2 className="max-w-[18ch] font-serif text-[32px] font-semibold leading-tight text-white">
          Your habits, finances, and study — one forecast.
        </h2>
        <p className="mt-4 max-w-[36ch] text-[15px] leading-relaxed text-white/75">
          Digital Twin learns from what you log and predicts where you're headed, so you can
          adjust before the month closes instead of after.
        </p>
      </div>

      <div className="flex w-full flex-1 items-center justify-center overflow-y-auto p-6">
        <div className="w-full max-w-sm">

          <div className="mb-6">
            <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400">
              Digital Twin AI
            </p>

            <h1 className="mt-2 text-2xl font-semibold text-slate-800 dark:text-slate-100">
              Welcome Back
            </h1>

            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Login to continue
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">

          {/* Email */}
          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">
              Email
            </label>

            <Input
              type="email"
              name="email"
              placeholder="Enter Email"
              value={formData.email}
              onChange={handleChange}
              required
            />
          </div>

          {/* Password */}
          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">
              Password
            </label>

            <div className="relative">
              <Input
                type={showPassword ? "text" : "password"}
                name="password"
                placeholder="Enter Password"
                value={formData.password}
                onChange={handleChange}
                required
                className="pr-11"
              />

              <button
                type="button"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-white/10 dark:text-slate-400"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={
                  showPassword ? "Hide password" : "Show password"
                }
              >
                {showPassword ? (
                  <EyeOff size={16} />
                ) : (
                  <Eye size={16} />
                )}
              </button>
            </div>
          </div>

          {/* Remember Me + Forgot Password */}
          <div className="flex items-center justify-between text-sm">

            <label className="flex cursor-pointer items-center gap-2 text-slate-500 dark:text-slate-400">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={handleRememberMeChange}
                className="h-4 w-4 cursor-pointer rounded border-slate-300 text-indigo-600 dark:text-indigo-400 focus:ring-indigo-500"
              />

              Remember Me
            </label>

            <Link
              to="/forgot-password"
              className="font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
            >
              Forgot Password?
            </Link>

          </div>

          {/* Login Button */}
          <Button
            type="submit"
            disabled={isLoading}
            className="w-full"
          >
            {isLoading ? "Logging in..." : "Login"}
          </Button>

        </form>

        <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
          Don't have an account?{" "}

          <Link
            to="/signup"
            className="font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
          >
            Sign Up
          </Link>
        </p>

        </div>
      </div>

    </div>
  );
}

export default Login;