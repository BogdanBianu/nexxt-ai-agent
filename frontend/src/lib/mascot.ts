// Canalul prin care orice parte a aplicației îi dă mascotei o replică. Proprietar: Om4.
export const MASCOT_EVENT = "lexops:mascot";

export const say = (text: string) => window.dispatchEvent(new CustomEvent<string>(MASCOT_EVENT, { detail: text }));
