import "./globals.css";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.92),transparent_26%),linear-gradient(135deg,#fcfbf7_0%,#f3f1ea_48%,#f7f6f1_100%)] [font-family:Hellix,'Helvetica_Neue',Arial,sans-serif] text-[#080808] antialiased">
        {children}
      </body>
    </html>
  );
}
