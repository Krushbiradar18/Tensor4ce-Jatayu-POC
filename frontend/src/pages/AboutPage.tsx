import PublicLayout from "@/components/PublicLayout";
import { ShieldCheck, Cpu, Brain, Zap, Target } from "lucide-react";

export default function AboutPage() {
  return (
    <PublicLayout>
      <div className="bg-hero-gradient py-24">
        <div className="container mx-auto px-4 text-center">
          <h1 className="text-5xl md:text-6xl font-bold font-display text-primary-foreground mb-6">About Tensor Bank</h1>
          <p className="text-xl text-primary-foreground/80 max-w-3xl mx-auto font-light leading-relaxed">
            Leading the future of modern finance. We are a digital-first institution providing next-generation financial services, making banking fast, secure, and accessible for everyone.
          </p>
        </div>
      </div>
      <div className="container mx-auto px-4 py-24">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12">
          {[
            { icon: ShieldCheck, title: "Modern Security", desc: "Advanced protection with real-time fraud prevention." },
            { icon: Cpu, title: "Smart Core", desc: "Powered by modern digital technology for deep financial analysis." },
            { icon: Brain, title: "Personalized", desc: "Advanced modeling to provide financial products tailored to you." },
            { icon: Target, title: "Instant Access", desc: "Processing times reduced from days to just a few minutes." },
          ].map((item) => (
            <div key={item.title} className="text-center group">
              <div className="w-16 h-16 bg-primary/5 rounded-2xl flex items-center justify-center mx-auto mb-6 group-hover:bg-accent-gradient group-hover:text-primary-foreground transition-all duration-300">
                <item.icon className="h-8 w-8 text-primary group-hover:text-inherit" />
              </div>
              <h3 className="text-xl font-bold text-foreground mb-3 font-display">{item.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </PublicLayout>
  );
}
