// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Errors with a code and a message written for the person using the app (as in core/models.py).

export class ScanError extends Error {
  /** @param {string} code  e.g. NO_INPUT, TOO_FEW_PHOTOS, NO_OUTLINE, NO_MODEL, ENGINE_CRASHED */
  constructor(code, userMessage, detail = '') {
    super(userMessage);
    this.name = 'ScanError';
    this.code = code;
    this.userMessage = userMessage;
    this.detail = detail;
  }
}

export class Cancelled extends Error {
  constructor() { super('Cancelled'); this.name = 'Cancelled'; }
}
