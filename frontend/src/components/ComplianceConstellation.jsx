import { Activity, BadgeCheck, BookOpenCheck, FileCheck2, LockKeyhole, Network, SearchCheck, ShieldCheck } from "lucide-react";

export function ComplianceConstellation() {
  return (
    <div className="constellation" aria-label="Animated ComplianceNexus concept visual">
      <div className="orbit orbit-one" />
      <div className="orbit orbit-two" />
      <div className="orbit orbit-three" />
      <div className="pulse-beam beam-one" />
      <div className="pulse-beam beam-two" />
      <div className="pulse-beam beam-three" />
      <div className="core-word">
        <span>COMPLIANCE</span>
        <strong>NEXUS</strong>
      </div>
      <div className="concept-item item-policy"><ShieldCheck size={28} /><span>Policies</span></div>
      <div className="concept-item item-reg"><Activity size={28} /><span>Regulations</span></div>
      <div className="concept-item item-law"><BadgeCheck size={28} /><span>Law</span></div>
      <div className="concept-item item-rules"><LockKeyhole size={28} /><span>Rules</span></div>
      <div className="concept-item item-standards"><FileCheck2 size={28} /><span>Standards</span></div>
      <div className="concept-item item-transparency"><SearchCheck size={28} /><span>Transparency</span></div>
      <div className="concept-item item-lineage"><Network size={28} /><span>Lineage</span></div>
      <div className="concept-item item-cert"><BookOpenCheck size={28} /><span>Citations</span></div>
      <div className="floating-verdict">
        <small>TX_1001</small>
        <strong>NON_COMPLIANT</strong>
        <span>$300K variance detected</span>
      </div>
    </div>
  );
}
