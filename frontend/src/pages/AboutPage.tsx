import PublicLayout from "@/components/PublicLayout";
import { Shield, Users, Award, Target } from "lucide-react";

export default function AboutPage() {
  return (
    <PublicLayout>
      <div className="bg-hero-gradient py-16">
        <div className="container mx-auto px-4 text-center">
          <h1 className="text-4xl font-bold font-display text-primary-foreground mb-4">About BankEase</h1>
          <p className="text-primary-foreground/80 max-w-2xl mx-auto">Pioneering digital banking solutions in India since 2010, serving millions of customers with trust and innovation.</p>
        </div>
      </div>
      <div className="container mx-auto px-4 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          {[
            { icon: Shield, title: "Trust", desc: "RBI-regulated with highest security standards" },
            { icon: Users, title: "2M+ Customers", desc: "Trusted by over two million customers nationwide" },
            { icon: Award, title: "Award Winning", desc: "Best Digital Lending Platform 2024" },
            { icon: Target, title: "Fast Processing", desc: "Average approval time under 48 hours" },
          ].map((item) => (
            <div key={item.title} className="text-center">
              <div className="w-14 h-14 bg-secondary rounded-full flex items-center justify-center mx-auto mb-4">
                <item.icon className="h-7 w-7 text-primary" />
              </div>
              <h3 className="font-semibold text-foreground mb-2">{item.title}</h3>
              <p className="text-sm text-muted-foreground">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </PublicLayout>
  );
}
