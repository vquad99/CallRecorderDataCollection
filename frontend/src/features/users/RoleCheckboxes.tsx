import { ROLE_CODES, ROLE_LABELS } from "../../api/admin";

export function RoleCheckboxes({
  value,
  onChange,
}: {
  value: string[];
  onChange: (roles: string[]) => void;
}) {
  return (
    <fieldset className="field">
      <legend className="field__label">Roles</legend>
      {ROLE_CODES.map((code) => (
        <label key={code} className="checkbox">
          <input
            type="checkbox"
            checked={value.includes(code)}
            onChange={(e) =>
              onChange(e.target.checked ? [...value, code] : value.filter((r) => r !== code))
            }
          />
          {ROLE_LABELS[code]}
        </label>
      ))}
    </fieldset>
  );
}
