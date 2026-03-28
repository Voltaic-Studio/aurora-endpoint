import "./globals.css";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-black [font-family:Hellix,'Helvetica_Neue',Arial,sans-serif] text-white antialiased">
        {children}
      </body>
    </html>
  );
}
