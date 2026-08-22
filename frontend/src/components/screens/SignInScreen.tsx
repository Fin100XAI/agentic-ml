// Sign-in, front-of-house only.
//
// There is no authentication behind this and the screen says so. What it
// does buy is attribution: the name given here rides on every request as
// X-Actor, so approvals in the activity log read "A. Patil, Revenue" instead
// of "user". For a system whose whole claim is that a human approved each
// step, a trail that cannot name the human is worth very little.
import { useState } from "react";
import { ArrowLeft, ArrowRight, ShieldAlert } from "lucide-react";

export interface Identity {
  name: string;
  department: string;
  label: string;
}

const DEPARTMENTS = [
  "Revenue",
  "Health",
  "Education",
  "Rural Development",
  "Urban Development",
  "Agriculture",
  "Finance",
  "Planning",
  "Other",
];

export function SignInScreen({
  onSignedIn,
  onBack,
}: {
  onSignedIn: (who: Identity) => void;
  onBack: () => void;
}) {
  const [name, setName] = useState("");
  const [department, setDepartment] = useState(DEPARTMENTS[0]);
  const [touched, setTouched] = useState(false);

  const clean = name.trim();
  const valid = clean.length >= 2;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!valid) return;
    onSignedIn({
      name: clean,
      department,
      label: `${clean}, ${department}`,
    });
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-16">
      <div className="w-full max-w-md">
        <button
          onClick={onBack}
          className="mb-8 inline-flex items-center gap-1.5 text-xs text-ink-dim transition-colors hover:text-accent"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </button>

        <p className="maha-eyebrow">Maha AI Intelligence Foundry</p>
        <h1 className="maha-rule mt-2 text-2xl text-ink md:text-[28px]">Sign in</h1>

        <form onSubmit={submit} className="mt-8 space-y-5">
          <div>
            <label htmlFor="si-name" className="block text-xs font-semibold text-ink">
              Your name
            </label>
            <input
              id="si-name"
              value={name}
              autoFocus
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. A. Patil"
              aria-invalid={touched && !valid}
              aria-describedby={touched && !valid ? "si-name-err" : undefined}
              className="mt-1.5 w-full rounded border border-edge bg-panel px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent"
            />
            {touched && !valid && (
              <p id="si-name-err" className="mt-1.5 text-[11px] text-bad">
                Please enter a name - it is what the audit trail will show.
              </p>
            )}
          </div>

          <div>
            <label htmlFor="si-dept" className="block text-xs font-semibold text-ink">
              Department
            </label>
            <select
              id="si-dept"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="mt-1.5 w-full rounded border border-edge bg-panel px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent"
            >
              {DEPARTMENTS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>

          <button type="submit" className="maha-cta inline-flex w-full items-center justify-center gap-2">
            Enter the workspace <ArrowRight className="h-4 w-4" />
          </button>
        </form>

        {/* Said plainly rather than buried: pretending to security you do
            not have is worse than having none. */}
        <div className="mt-8 flex items-start gap-2.5 rounded-[14px] border border-edge bg-panel-2 px-4 py-3.5">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <p className="text-[11px] leading-relaxed text-ink-dim">
            <span className="font-semibold text-ink">This is not a security check.</span>{" "}
            There is no password and nothing is verified. The name is recorded against
            everything you approve so the audit trail names a person - it grants no
            access and protects nothing. Real accounts would be a separate piece of work.
          </p>
        </div>
      </div>
    </div>
  );
}
