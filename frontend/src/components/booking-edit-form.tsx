"use client";

import { useState } from "react";
import { SaveIcon, XIcon } from "lucide-react";

import type { BookingWithDocument, BookingUpdate } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface BookingEditFormProps {
  booking: BookingWithDocument;
  onSave: (id: string, data: BookingUpdate) => Promise<void>;
  onCancel: () => void;
}

export function BookingEditForm({ booking, onSave, onCancel }: BookingEditFormProps) {
  const [account, setAccount] = useState(booking.account);
  const [contraAccount, setContraAccount] = useState(booking.contra_account);
  const [buKey, setBuKey] = useState(booking.bu_key ?? "");
  const [bookingText, setBookingText] = useState(booking.booking_text ?? "");
  const [amount, setAmount] = useState(booking.amount);
  const [debitCredit, setDebitCredit] = useState(booking.debit_credit);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(booking.id, {
        account,
        contra_account: contraAccount,
        bu_key: buKey || null,
        booking_text: bookingText || null,
        amount,
        debit_credit: debitCredit,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`account-${booking.id}`}>Konto</Label>
          <Input
            id={`account-${booking.id}`}
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            placeholder="z.B. 6815"
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`contra-${booking.id}`}>Gegenkonto</Label>
          <Input
            id={`contra-${booking.id}`}
            value={contraAccount}
            onChange={(e) => setContraAccount(e.target.value)}
            placeholder="z.B. 1200"
            required
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`amount-${booking.id}`}>Betrag</Label>
          <Input
            id={`amount-${booking.id}`}
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>S/H</Label>
          <Select value={debitCredit} onValueChange={(v) => v && setDebitCredit(v)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="S">S (Soll)</SelectItem>
              <SelectItem value="H">H (Haben)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`bukey-${booking.id}`}>BU-Schlüssel</Label>
          <Input
            id={`bukey-${booking.id}`}
            value={buKey}
            onChange={(e) => setBuKey(e.target.value)}
            placeholder="z.B. 9"
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`text-${booking.id}`}>Buchungstext</Label>
        <Input
          id={`text-${booking.id}`}
          value={bookingText}
          onChange={(e) => setBookingText(e.target.value)}
          maxLength={60}
          placeholder="max. 60 Zeichen"
        />
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={saving}>
          <XIcon className="size-3.5" />
          Abbrechen
        </Button>
        <Button type="submit" size="sm" disabled={saving}>
          <SaveIcon className="size-3.5" />
          {saving ? "Wird gespeichert…" : "Speichern"}
        </Button>
      </div>
    </form>
  );
}
