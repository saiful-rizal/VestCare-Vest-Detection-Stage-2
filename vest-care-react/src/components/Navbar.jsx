import ProfileMenu from "./ProfileMenu";

export default function Navbar({ device, position }) {
  return (
    <nav className="relative flex flex-wrap items-center justify-between px-0 py-2 mx-6 transition-all ease-in shadow-none duration-250 rounded-2xl lg:flex-nowrap lg:justify-start">
      <div className="flex items-center justify-between w-full px-4 py-1 mx-auto flex-wrap-inherit">
        <nav>
          <ol className="flex flex-wrap pt-1 mr-12 bg-transparent rounded-lg sm:mr-16">
            <li className="text-sm leading-normal">
              <a className="text-white opacity-50" href="#">Pages</a>
            </li>
            <li className="text-sm pl-2 capitalize leading-normal text-white before:float-left before:pr-2 before:text-white before:content-['/']" aria-current="page">Dashboard</li>
          </ol>
          <h6 className="mb-0 font-bold text-white capitalize">Dashboard</h6>
        </nav>
        <div className="flex items-center mt-2 grow sm:mt-0 sm:mr-6 md:mr-0 lg:flex lg:basis-auto">
          <div className="md:ml-auto"></div>
          <ul className="flex flex-row items-center justify-end pl-0 mb-0 list-none md-max:w-full">
            <ProfileMenu device={device} position={position} />
          </ul>
        </div>
      </div>
    </nav>
  );
}
