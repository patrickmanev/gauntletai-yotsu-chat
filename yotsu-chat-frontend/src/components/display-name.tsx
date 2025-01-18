interface DisplayNameProps {
    name: string;
    isOnline?: boolean;
  }
  
  export function DisplayName({ name, isOnline = false }: DisplayNameProps) {
    return (
      <span className={`${isOnline ? 'text-green-600 font-semibold' : ''}`}>
        {name}
      </span>
    )
  }