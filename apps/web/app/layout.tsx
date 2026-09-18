import "./style.css";
import "./brand.css";
import { brand } from "./brand";
export const metadata = {title: {default: brand.name, template: `%s | ${brand.name}`}, description: brand.description,
  applicationName: brand.name, icons: {icon: "/brand/quiblyx-mark.svg", shortcut: "/brand/quiblyx-mark.svg"}};
export default function RootLayout({children}: {children: React.ReactNode}) {
  return <html lang="en"><body>{children}</body></html>;
}
