import './globals.css';

export const metadata = {
  title: 'Creator Analytics RAG | Video Intelligence Platform',
  description: 'Compare two social media videos with AI-powered RAG chatbot — engagement analytics, transcript analysis, and actionable insights.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
