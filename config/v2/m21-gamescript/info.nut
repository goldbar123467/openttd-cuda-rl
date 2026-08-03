class M21CoverageInfo extends GSInfo {
	function GetAuthor()      { return "OpenTTD-RL"; }
	function GetName()        { return "M21CoverageFixture"; }
	function GetShortName()   { return "M21C"; }
	function GetDescription() { return "Pinned passive Game Script fixture for M21 command and save/load qualification."; }
	function GetVersion()     { return 1; }
	function GetAPIVersion()  { return "15"; }
	function GetDate()        { return "2026-08-02"; }
	function CreateInstance() { return "M21Coverage"; }
}

RegisterGS(M21CoverageInfo());
