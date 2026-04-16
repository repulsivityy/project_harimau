import type { Metadata } from "next";
import { Space_Grotesk, Epilogue } from "next/font/google";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
});

const epilogue = Epilogue({
  subsets: ["latin"],
  variable: "--font-epilogue",
});

export const metadata: Metadata = {
  title: "HARIMAU // THREAT_HUNTING_CORE",
  description: "AI-powered threat hunting platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${epilogue.variable} h-full antialiased dark`}
    >
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
        />
      </head>
      <body className="font-body selection:bg-primary selection:text-on-primary min-h-screen bg-surface text-foreground">
        {children}
      </body>
    </html>
  );
}
