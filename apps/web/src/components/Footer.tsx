// src/components/Footer.tsx
import { Github, Linkedin } from "lucide-react";

export default function Footer() {
  return (
    <footer className="w-full border-t border-border bg-background/80 backdrop-blur-sm mt-16">
      <div className="container mx-auto px-8 py-6 flex flex-col md:flex-row items-center justify-between text-sm text-muted-foreground">
        {/* Sol kısım */}
        <p className="text-center md:text-left">
          © {new Date().getFullYear()} <span className="font-semibold text-primary">Censorly</span>. All rights reserved.
        </p>

        {/* Sağ kısım */}
        <div className="flex items-center gap-6 mt-3 md:mt-0">
          <a
            href="https://github.com/AI-by-DI/Censorly"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-primary transition-colors"
          >
            <Github className="w-4 h-4" /> GitHub
          </a>

          {/* İlayda LinkedIn */}
          <a
            href="https://www.linkedin.com/in/ilayda-akyuz/"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-primary transition-colors"
          >
            <Linkedin className="w-4 h-4" /> İlayda Akyüz
          </a>

          {/* Didar'ın LinkedIn */}
          <a
            href="https://www.linkedin.com/in/didar-nur-bilgin/"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-primary transition-colors"
          >
            <Linkedin className="w-4 h-4" /> Didar Nur Bilgin
          </a>
        </div>
      </div>
    </footer>
  );
}
