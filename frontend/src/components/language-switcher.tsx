"use client";

import { useLocale } from "next-intl";
import { useRouter, usePathname } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const LOCALE_LABELS: Record<string, string> = {
  de: "Deutsch",
  en: "English",
};

export function LanguageSwitcher() {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  function handleChange(newLocale: string | null) {
    if (newLocale) {
      router.replace(pathname, { locale: newLocale });
    }
  }

  return (
    <Select value={locale} onValueChange={handleChange}>
      <SelectTrigger className="h-8 w-[110px] text-xs" size="sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {routing.locales.map((loc) => (
          <SelectItem key={loc} value={loc} className="text-xs">
            {LOCALE_LABELS[loc] ?? loc}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
