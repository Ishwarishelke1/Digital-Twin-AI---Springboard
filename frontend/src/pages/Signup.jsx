import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import { Eye, EyeOff } from "lucide-react";

import { registerUser } from "../services/authService";
import { useAuth } from "../context/useAuth";
import { useForceLightTheme } from "../hooks/useForceLightTheme";
import SilkBackground from "../components/SilkBackground";
import SplitHeading from "../components/ui/SplitHeading";
import { Input, Select } from "../components/ui/Field";
import Button from "../components/ui/Button";
import { getApiErrorMessage } from "../utils/apiError";

function Signup() {
  const navigate = useNavigate();
  const { login } = useAuth();
  useForceLightTheme();

  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
    age: "",
    gender: "",
    profession: "Student",
    monthly_income_baseline: "",
    risk_tolerance: "MODERATE",
  });

  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleChange = (e) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (formData.password !== formData.confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }

    const age = Number(formData.age);
    if (!formData.age || Number.isNaN(age) || age < 13 || age > 120) {
      toast.error("Age must be between 13 and 120.");
      return;
    }

    setIsLoading(true);

    try {
      const payload = {
        name: formData.name,
        email: formData.email,
        password: formData.password,
        age,
        gender: formData.gender || undefined,
        monthly_income_baseline: formData.monthly_income_baseline !== ""
          ? Number(formData.monthly_income_baseline)
          : 0,
        occupation: formData.profession,
        risk_tolerance: formData.risk_tolerance,
      };

      const data = await registerUser(payload);
      await login(data);
      navigate("/dashboard");
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Registration failed. Please try again."));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full bg-white dark:bg-slate-800">

      {/* Brand panel — hidden below md, mirrors Login's split layout. Fills
          the full window height on its half (independent of the form
          column's scroll) rather than floating as a centered card, so the
          page always fills the browser window. */}
      <div className="relative hidden w-1/2 shrink-0 flex-col justify-center overflow-hidden bg-gradient-to-br from-indigo-700 to-indigo-600 px-16 text-white md:flex">
        <SilkBackground />
        <div className="relative z-10">
          <img
            src="/logo-icon.png"
            alt="Digital Twin AI"
            className="mb-7 h-28 w-28 object-contain drop-shadow-[0_0_16px_rgba(255,255,255,0.55)]"
          />
          <h2 className="max-w-[18ch] font-serif text-[32px] font-semibold leading-tight text-white">
            Start building the twin that predicts what's next.
          </h2>
          <p className="mt-4 max-w-[36ch] text-[15px] leading-relaxed text-white/75">
            A few details now, and Digital Twin AI starts forecasting your savings, study score,
            and habit consistency from day one.
          </p>
        </div>
      </div>

      {/* Form column scrolls independently — Signup's field count regularly
          exceeds one screen's height, so this column (not the whole page)
          is what scrolls, keeping the brand panel fixed at full height. */}
      <div className="w-full flex-1 overflow-y-auto p-6 sm:p-10">
        <div className="mx-auto w-full max-w-sm py-6">
        <div className="mb-6">
          <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400">Digital Twin AI</p>
          <SplitHeading as="h1" text="Create Account" className="mt-2 text-2xl font-semibold text-slate-800 dark:text-slate-100" />
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Create your new account</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Full Name</label>
            <Input
              type="text"
              name="name"
              placeholder="Enter Full Name"
              value={formData.name}
              onChange={handleChange}
              required
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Email</label>
            <Input
              type="email"
              name="email"
              placeholder="Enter Email"
              value={formData.email}
              onChange={handleChange}
              required
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Password</label>
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
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Confirm Password</label>
            <div className="relative">
              <Input
                type={showPassword ? "text" : "password"}
                name="confirmPassword"
                placeholder="Confirm Password"
                value={formData.confirmPassword}
                onChange={handleChange}
                required
                className="pr-11"
              />
              <button
                type="button"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-white/10 dark:text-slate-400"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Age</label>
            <Input
              type="number"
              name="age"
              placeholder="Enter Age"
              min="13"
              max="120"
              step="1"
              value={formData.age}
              onChange={handleChange}
              required
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Gender</label>
            <Select name="gender" value={formData.gender} onChange={handleChange}>
              <option value="">Select Gender</option>
              <option value="MALE">Male</option>
              <option value="FEMALE">Female</option>
              <option value="NON_BINARY">Non-binary</option>
              <option value="PREFER_NOT_TO_SAY">Prefer not to say</option>
            </Select>
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Profession</label>
            <Select name="profession" value={formData.profession} onChange={handleChange}>
              <option value="Student">Student</option>
              <option value="Employee">Employee</option>
              <option value="Freelancer">Freelancer</option>
            </Select>
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Monthly Income (₹)</label>
            <Input
              type="number"
              name="monthly_income_baseline"
              placeholder="Monthly Income (optional)"
              min="0"
              step="0.01"
              value={formData.monthly_income_baseline}
              onChange={handleChange}
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">Risk Tolerance</label>
            <Select name="risk_tolerance" value={formData.risk_tolerance} onChange={handleChange}>
              <option value="CONSERVATIVE">Conservative</option>
              <option value="MODERATE">Moderate</option>
              <option value="AGGRESSIVE">Aggressive</option>
            </Select>
          </div>

          <Button type="submit" disabled={isLoading} className="w-full">
            {isLoading ? "Creating Account..." : "Create Account"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
          Already have an account?{" "}
          <Link to="/login" className="font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
            Login
          </Link>
        </p>
        </div>
      </div>

    </div>
  );
}

export default Signup;
