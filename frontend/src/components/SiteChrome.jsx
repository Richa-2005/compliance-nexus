import { ShieldCheck } from "lucide-react";
import { GithubMark } from "./GithubMark";

export function Footer() {
  return (
    <footer>
      <div>
        <a className="brand" href="/"><ShieldCheck size={20} /> ComplianceNexus</a>
        <p>RAG-powered audit intelligence for cross-border compliance decisions.</p>
      </div>
      <nav>
        <a href="/#flow">Audit Flow</a>
        <a href="/login">Login</a>
        <a href="/signup">Sign Up</a>
      </nav>
      <div className="footer-built">
        <span>Built by Richa Gupta</span>
        <a href="https://github.com/Richa-2005" target="_blank" rel="noreferrer" aria-label="Richa Gupta on GitHub">
          <GithubMark size={20} />
        </a>
      </div>
    </footer>
  );
}

export function BrandNav({ children }) {
  return (
    <nav className="nav">
      <a className="brand" href="/"><ShieldCheck size={22} /> ComplianceNexus</a>
      {children}
    </nav>
  );
}
