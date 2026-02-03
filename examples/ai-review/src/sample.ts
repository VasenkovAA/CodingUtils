export function sum(a: number, b: number) {
  return a + b;
}

const runUnsafe = (cmd: string) => {
  // intentionally naive example
  return cmd;
}

export class Person {
  constructor(public name: string) {}
  greet() { return `Hi ${this.name}`; }
}
