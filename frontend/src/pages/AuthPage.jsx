import { ArrowRight, LockKeyhole, ShieldCheck, UserRoundCheck } from "lucide-react";
import { BrandNav } from "../components/SiteChrome";
import { routeTo } from "../utils/navigation";

export function AuthPage({ mode }) {
  const isSignup = mode === "signup";

  return (
    <main className="auth-page">
      <BrandNav />

      <section className="auth-layout">
        <div className="auth-panel">
          <span className="eyebrow"><LockKeyhole size={14} /> Secure Access</span>
          <h1>{isSignup ? "Create your ComplianceNexus workspace." : "Enter the compliance console."}</h1>
          <p>
            Use demo access to inspect the analyst workflow immediately, or continue with a standard account form.
          </p>

          <form className="auth-form" onSubmit={(event) => {
            event.preventDefault();
            routeTo("/dashboard?role=analyst");
          }}>
            {isSignup && <input type="text" placeholder="Full name" required />}
            <input type="email" placeholder="Work email" required />
            <input type="password" placeholder="Password" required minLength={6} />
            <button type="submit">{isSignup ? "Create Account" : "Login"} <ArrowRight size={17} /></button>
          </form>
          <p className="auth-toggle">
            {isSignup ? "Already have an account? " : "Don't have an account? "}
            <a href={isSignup ? "/login" : "/signup"}>{isSignup ? "Sign in" : "Sign up first"}</a>
          </p>

          <div className="demo-logins">
            <span className="eyebrow">Demo Logins</span>
            <button type="button" onClick={() => routeTo("/dashboard?role=analyst")}>
              <UserRoundCheck size={17} />
              Sarah Jenkins
              <em>L1 Analyst</em>
            </button>
            <button type="button" onClick={() => routeTo("/dashboard?role=officer")}>
              <ShieldCheck size={17} />
              Marcus Vance
              <em>L2 Risk Officer</em>
            </button>
          </div>
        </div>

        <aside className="auth-context">
          <h2>Built for regulatory review teams.</h2>
          <p>
            ComplianceNexus gives analysts and risk officers a shared workspace for transaction review,
            citation inspection, entity-policy lineage, and PDF evidence export.
          </p>
          <div className="role-summary">
            <div>
              <span>L1 Analyst</span>
              <ul>
                <li>Reviews newly evaluated remittances</li>
                <li>Opens cited policy pages and source anchors</li>
                <li>Escalates exceptions for legal or L2 review</li>
              </ul>
            </div>
            <div>
              <span>L2 Risk Officer</span>
              <ul>
                <li>Confirms high-risk breach decisions</li>
                <li>Blocks or approves exceptional remittances</li>
                <li>Exports evidence certificates for audit files</li>
              </ul>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}
