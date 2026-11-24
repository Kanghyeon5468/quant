import './globals.css';
export const metadata = { title: 'QuantCore · Research Terminal', description: 'Reproducible quantitative research. Explicitly synthetic demo data.' };
export default function Layout({children}: {children: React.ReactNode}) {
  return <html lang="ko"><body>{children}</body></html>;
}
