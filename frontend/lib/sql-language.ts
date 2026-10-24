export const SQL_LANGUAGES = [
  { value: "sql", label: "SQL (standard)" },
  { value: "plsql", label: "PL/SQL (Oracle)" },
  { value: "oracle", label: "Oracle SQL" },
  { value: "postgresql", label: "PostgreSQL" },
  { value: "mysql", label: "MySQL" },
  { value: "sqlserver", label: "SQL Server" },
  { value: "sqlite", label: "SQLite" }
] as const;

export type SqlLanguage = (typeof SQL_LANGUAGES)[number]["value"];

export function sqlLanguageLabel(language: SqlLanguage) {
  return SQL_LANGUAGES.find((option) => option.value === language)?.label ?? "SQL (standard)";
}
